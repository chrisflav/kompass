import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";

import { API_BASE } from "../api/client";
import type { Site } from "../api/site";
import type { TerminChoice, TerminEnums } from "../api/terminEnums";

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

/**
 * The deployment every test runs against. The chrome asks for this on every
 * page, so it belongs in the base handlers rather than in each test; a test
 * that cares about a different section overrides it with {@link useSite}.
 *
 * Typed against the generated contract, so a field the API drops or renames
 * breaks the fixture here rather than going unnoticed in the tests that use it.
 */
export const DEFAULT_SITE: Site = {
  name: "Ludwigsburg",
  display_name: "JDAV Ludwigsburg",
  dav_section: "Schwaben",
  street: "Musterweg 1",
  town: "71634 Ludwigsburg",
  telephone: "07141 123456",
  contact_mail: "info@example.org",
  responsible_mail: "verantwortlich@example.org",
  latitude: 48.8974,
  longitude: 9.1916,
};

/**
 * The Termin choice lists `/enums` serves. The SPA no longer carries them, so
 * this fixture stands in for `ludwigsburgalpin.models`; the second argument is
 * the field's model default, which a blank create form preselects.
 */
const choices = (
  options: [string, string][],
  defaultValue: string | null = null,
): TerminChoice[] =>
  options.map(([value, label]) => ({ value, label, default: value === defaultValue }));

export const TERMIN_ENUMS: TerminEnums = {
  // `group` has no model default, so nothing in its list is marked.
  group: choices([
    ["ASG", "Alpinsportgruppe"],
    ["OGB", "Ortsgruppe Bietigheim"],
    ["OGV", "Ortsgruppe Vaihingen"],
    ["JUG", "Jugend"],
    ["FAM", "Familie"],
    ["Ü30", "Ü30"],
    ["MTB", "Mountainbike"],
    ["RA", "RegioAktiv"],
    ["SEK", "Sektion"],
  ]),
  category: choices(
    [
      ["WAN", "Wandern"],
      ["BW", "Bergwandern"],
      ["KST", "Klettersteig"],
      ["KL", "Klettern"],
      ["SKI", "Piste, Loipe"],
      ["SCH", "Schneeschuhgehen"],
      ["ST", "Skitour"],
      ["STH", "Skihochtour"],
      ["HT", "Hochtour"],
      ["MTB", "Mountainbike"],
      ["AUS", "Ausbildung"],
      ["SON", "Sonstiges z.B. Treffen"],
    ],
    "SON",
  ),
  condition: choices(
    [
      ["gering", "gering"],
      ["mittel", "mittel"],
      ["groß", "groß"],
      ["sehr groß", "sehr groß"],
    ],
    "mittel",
  ),
  technik: choices(
    [
      ["leicht", "leicht"],
      ["mittel", "mittel"],
      ["schwer", "schwer"],
      ["sehr schwer", "sehr schwer"],
    ],
    "mittel",
  ),
  saison: choices(
    [
      ["ganzjährig", "ganzjährig"],
      ["Indoor", "Indoor"],
      ["Sommer", "Sommer"],
      ["Winter", "Winter"],
    ],
    "ganzjährig",
  ),
  eventart: choices(
    [
      ["Einzeltermin", "Einzeltermin"],
      ["Mehrtagesevent", "Mehrtagesevent"],
      ["Regelmäßiges Event/Training", "Regelmäßiges Event/Training"],
      ["Tagesevent", "Tagesevent"],
      ["Wochenendevent", "Wochenendevent"],
    ],
    "Einzeltermin",
  ),
  klassifizierung: choices(
    [
      ["Gemeinschaftstour", "Gemeinschaftstour"],
      ["Ausbildung", "Ausbildung"],
    ],
    "Gemeinschaftstour",
  ),
};

/** Handlers present in every test; individual tests override with `server.use`. */
const baseHandlers = [
  http.get(api("/api/members/me"), () => HttpResponse.json(DEFAULT_ME)),
  http.get(api("/api/startpage/public/site"), () => HttpResponse.json(DEFAULT_SITE)),
  // Every Termin form builds its selects from these, so they belong here
  // rather than in each test that opens one.
  http.get(api("/api/ludwigsburgalpin/enums"), () => HttpResponse.json(TERMIN_ENUMS)),
  http.get(api("/api/ludwigsburgalpin/public/enums"), () => HttpResponse.json(TERMIN_ENUMS)),
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

/** Replace `/api/startpage/public/site` for one test (e.g. another section). */
export function useSite(overrides: Partial<Site>) {
  server.use(
    http.get(api("/api/startpage/public/site"), () =>
      HttpResponse.json({ ...DEFAULT_SITE, ...overrides }),
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
