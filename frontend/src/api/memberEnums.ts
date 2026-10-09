import { client, unwrap } from "./http";
import { useApiQuery } from "./hooks";
import type { EnumChoice } from "./activityEnums";

/**
 * Gender choice options, fetched rather than mirrored in TypeScript. Served
 * without authentication: the waiting-list, registration and echo forms are
 * public, and the gender select is model metadata, not data about anyone.
 */
export type MemberEnums = Record<string, EnumChoice[]>;

/*
 * `staleTime: Infinity`: the list is immutable for a deployment, so there is
 * nothing to refetch, and a refetch that failed would take the form down with
 * it. See `terminEnums.ts` for the full reasoning.
 */

/** Gender options for the public self-service forms. */
export function usePublicMemberEnums() {
  return useApiQuery<MemberEnums>(
    ["members", "public", "enums"],
    () => unwrap(client.GET("/api/members/public/enums")),
    { staleTime: Infinity },
  );
}
