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
  is_superuser: boolean;
  /** Global permission codenames ("app.codename") the user holds. */
  permissions: string[];
}

async function fetchMe(): Promise<Me> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/members/me`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Konnte aktuelle Anmeldung nicht laden.");
  const me = (await res.json()) as Me;
  // Older backends did not send these; treat them as "no extra rights" rather
  // than letting `undefined` blow up a permission check.
  return { ...me, is_superuser: me.is_superuser ?? false, permissions: me.permissions ?? [] };
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

/**
 * Global permission check for hiding actions the backend would refuse.
 *
 * The Django admin hid buttons the user had no permission for; the SPA showed
 * every "Neu …" button unconditionally and let the click fail with a 403 after
 * the user had filled in a whole modal. This restores the admin's behaviour.
 *
 * Purely cosmetic: the API re-checks every request, and object-level rules
 * (which depend on the row) are still only decided server-side.
 */
export function usePermissions() {
  const me = useMe();
  const granted = me.data?.permissions;
  const superuser = me.data?.is_superuser ?? false;
  return {
    /** Whether the user holds every one of `codenames` ("app.codename"). */
    can: (...codenames: string[]) =>
      superuser || codenames.every((c) => granted?.includes(c) ?? false),
    /** Whether the user holds at least one of `codenames`. */
    canAny: (...codenames: string[]) =>
      superuser || codenames.some((c) => granted?.includes(c) ?? false),
    /** False until `/me` has answered, so nothing flashes before it is known. */
    loaded: granted !== undefined,
    isSuperuser: superuser,
  };
}
