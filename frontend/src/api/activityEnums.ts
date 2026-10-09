import { client, unwrap } from "./http";
import { useApiQuery } from "./hooks";
import type { components } from "./schema";

/**
 * Choice options for the Group/Freizeit/ActivityCategory/LJPProposal fields
 * used by the activities feature's forms (weekday, difficulty, tour
 * type/approach, LJP category/goal/reason), fetched rather than mirrored in
 * TypeScript.
 */

/** One option of an activities choice field; `default` marks the model default. */
export type EnumChoice = components["schemas"]["EnumChoice"];

/** The `/activities/enums` payload: one option list per choice field. */
export type ActivityEnums = Record<string, EnumChoice[]>;

/*
 * `staleTime: Infinity`: the lists are immutable for a deployment, so there is
 * nothing to refetch, and a refetch that failed would take the form down with
 * it. See `terminEnums.ts` for the full reasoning.
 */

/** Choice options for the activities management forms. */
export function useActivityEnums() {
  return useApiQuery<ActivityEnums>(
    ["members", "activities", "enums"],
    () => unwrap(client.GET("/api/members/activities/enums")),
    { staleTime: Infinity },
  );
}

/**
 * What a blank create form preselects for `field`. The backend marks the
 * model default, and a field without one falls back to its first option
 * rather than to a value the SPA would have to know by heart. Most fields are
 * integer choices; `ljp_category` is the one string field.
 */
export function defaultChoice(enums: ActivityEnums, field: string): string | number {
  const options = enums[field] ?? [];
  const picked = options.find((o) => o.default) ?? options[0];
  return (picked?.value as string | number) ?? "";
}

/** `{value, label}` options for `<Select>`/`<ChoiceSelect>`, cast to a concrete value type. */
export function selectOptions<T extends string | number>(
  enums: ActivityEnums,
  field: string,
): { value: T; label: string }[] {
  return (enums[field] ?? []).map((o) => ({ value: o.value as T, label: o.label }));
}
