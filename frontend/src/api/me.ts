import { useQuery } from "@tanstack/react-query";

import { getToken } from "../auth";
import { API_BASE } from "./client";

/** The authenticated user's identity, from `GET /api/members/me`. */
export interface Me {
  user_id: number;
  username: string;
  name: string;
  /** null for accounts without a linked Member (e.g. a pure admin login). */
  member_id: number | null;
  is_staff: boolean;
}

async function fetchMe(): Promise<Me> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/members/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Konnte aktuelle Anmeldung nicht laden.");
  return (await res.json()) as Me;
}

/**
 * The current user. Fetched once the token exists; cached for the session. Kept
 * outside the openapi-fetch client (like the login call) so adding the `/me`
 * route needs no schema regeneration.
 */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    enabled: Boolean(getToken()),
    staleTime: 5 * 60_000,
    retry: false,
  });
}
