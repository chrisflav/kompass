import { client, unwrap } from "./http";
import { useApiQuery } from "./hooks";
import type { components } from "./schema";

/**
 * Termin choice options, fetched rather than mirrored. The option lists are
 * deployment-specific (a section names its own Ortsgruppen), so no form may
 * hardcode them — both `/enums` endpoints serve `ludwigsburgalpin.models`
 * verbatim, keyed by field name.
 */

/** One option of a Termin choice field; `default` marks the model default. */
export type TerminChoice = components["schemas"]["TerminEnumChoice"];

/** The `/enums` payload: one option list per Termin choice field. */
export type TerminEnums = Record<string, TerminChoice[]>;

/*
 * `staleTime: Infinity` on both: the lists are immutable for a deployment, so
 * there is nothing to refetch, and a refetch that failed would take the form
 * down with it. `QueryBoundary` reads `error` before `data`, and React Query
 * keeps `data` while setting `error` on a failed background refetch, so a
 * stale-then-refocus cycle on flaky mobile data would swap a filled-in form
 * for an error state and unmount everything the user had typed.
 */

/** Choice options for the authenticated Termin management forms. */
export function useTerminEnums() {
  return useApiQuery<TerminEnums>(
    ["ludwigsburgalpin", "enums"],
    () => unwrap(client.GET("/api/ludwigsburgalpin/enums")),
    { staleTime: Infinity },
  );
}

/** The same lists without a bearer token, for the public submission flow. */
export function usePublicTerminEnums() {
  return useApiQuery<TerminEnums>(
    ["ludwigsburgalpin", "public", "enums"],
    () => unwrap(client.GET("/api/ludwigsburgalpin/public/enums")),
    { staleTime: Infinity },
  );
}

/**
 * What a blank create form preselects for `field`. Both forms always send every
 * choice field, so they need a concrete starting point; the backend marks the
 * model default, and a field without one (`group`) falls back to its first
 * option rather than to a value the SPA would have to know by heart.
 */
export function defaultChoice(enums: TerminEnums, field: string): string {
  const options = enums[field] ?? [];
  return (options.find((o) => o.default) ?? options[0])?.value ?? "";
}
