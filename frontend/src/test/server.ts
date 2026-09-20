import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { API_BASE } from "../api/client";

/** Absolute URL for an API path, so handlers match what the client actually calls. */
export const api = (path: string) => `${API_BASE}${path}`;

/**
 * The identity every test starts from: a staff member with a handful of
 * permissions but no superuser flag, so permission gating is exercised by
 * default rather than short-circuited.
 */
export const DEFAULT_ME = {
  user_id: 2,
  username: "hannah.becker",
  name: "Hannah Beckers",
  member_id: 7,
  is_staff: true,
  is_superuser: false,
  permissions: [
    "members.add_global_member",
    "members.change_global_member",
    "members.delete_global_member",
    "members.add_group",
    "members.delete_group",
    "members.add_membernotelist",
    "members.add_global_freizeit",
    "members.change_global_memberwaitinglist",
    "finance.add_global_statement",
    "auth.view_user",
    "auth.add_user",
    "auth.change_user",
    "auth.delete_user",
  ],
};

/** Handlers present in every test; individual tests override with `server.use`. */
const baseHandlers = [
  http.get(api("/api/members/me"), () => HttpResponse.json(DEFAULT_ME)),
];

export const server = setupServer(...baseHandlers);

/* --- helpers for the common overrides ------------------------------------ */

/** Replace `/api/members/me` for one test (e.g. to drop a permission). */
export function useMe(overrides: Partial<typeof DEFAULT_ME>) {
  server.use(
    http.get(api("/api/members/me"), () =>
      HttpResponse.json({ ...DEFAULT_ME, ...overrides }),
    ),
  );
}

/** A 403 shaped exactly like the permission layer's: a bare codename. */
export function forbidden(path: string, codename: string) {
  server.use(
    http.get(api(path), () => HttpResponse.json({ detail: codename }, { status: 403 })),
  );
}

/** A django-ninja request-validation 422 (a list of pydantic error objects). */
export function ninjaValidation(
  items: { loc: (string | number)[]; msg: string; type: string }[],
) {
  return HttpResponse.json({ detail: items }, { status: 422 });
}

/** Our own `ValidationError` 422 (flat messages plus a per-field map). */
export function djangoValidation(errors: Record<string, string[]>) {
  return HttpResponse.json(
    { detail: Object.values(errors).flat(), errors },
    { status: 422 },
  );
}

/** The file names in a multipart request body, in order. */
export async function multipartFilenames(request: Request): Promise<string[]> {
  const fd = await request.formData();
  return [...fd.values()].filter((v): v is File => v instanceof File).map((f) => f.name);
}

/** The plain (non-file) fields of a multipart request body. */
export async function multipartFields(request: Request): Promise<Record<string, string>> {
  const fd = await request.formData();
  const out: Record<string, string> = {};
  for (const [k, v] of fd.entries()) {
    if (typeof v === "string") out[k] = v;
  }
  return out;
}

export { http, HttpResponse };
