import { act, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { usePermissions, useMe } from "./me";
import { renderHookWithApp } from "../test/utils";
import { api, http, HttpResponse, server, useMe as mockMe } from "../test/server";

describe("usePermissions", () => {
  it("reports the caller's granted permissions", async () => {
    const { captured } = renderHookWithApp(() => usePermissions());
    await waitFor(() => expect(captured.current?.loaded).toBe(true));
    expect(captured.current?.can("members.add_group")).toBe(true);
    expect(captured.current?.can("finance.add_ledger")).toBe(false);
  });

  it("requires every codename passed to `can`", async () => {
    const { captured } = renderHookWithApp(() => usePermissions());
    await waitFor(() => expect(captured.current?.loaded).toBe(true));
    expect(captured.current?.can("members.add_group", "members.add_global_member")).toBe(true);
    expect(captured.current?.can("members.add_group", "finance.add_ledger")).toBe(false);
  });

  it("requires only one codename for `canAny`", async () => {
    const { captured } = renderHookWithApp(() => usePermissions());
    await waitFor(() => expect(captured.current?.loaded).toBe(true));
    expect(captured.current?.canAny("finance.add_ledger", "members.add_group")).toBe(true);
    expect(captured.current?.canAny("finance.add_ledger", "startpage.add_post")).toBe(false);
  });

  it("grants everything to a superuser without listing permissions", async () => {
    // The backend sends an empty list for superusers precisely because the flag
    // already answers every question.
    mockMe({ is_superuser: true, permissions: [] });
    const { captured } = renderHookWithApp(() => usePermissions());
    await waitFor(() => expect(captured.current?.loaded).toBe(true));
    expect(captured.current?.isSuperuser).toBe(true);
    expect(captured.current?.can("anything.at_all")).toBe(true);
  });

  it("denies everything until /me has answered, so nothing flashes", () => {
    const { captured } = renderHookWithApp(() => usePermissions());
    expect(captured.current?.loaded).toBe(false);
    expect(captured.current?.can("members.add_group")).toBe(false);
    expect(captured.current?.canAny("members.add_group", "auth.view_user")).toBe(false);
  });

  it("treats a backend without the permissions field as holding none", async () => {
    // Guards the rollout window where an older API answers `/me`.
    mockMe({ permissions: undefined as unknown as string[] });
    const { captured } = renderHookWithApp(() => usePermissions());
    await waitFor(() => expect(captured.current?.loaded).toBe(true));
    expect(captured.current?.can("members.add_group")).toBe(false);
    expect(captured.current?.isSuperuser).toBe(false);
  });
});

describe("useMe fallbacks", () => {
  it("treats a backend that omits the new fields as having no extra rights", async () => {
    // Older deployments answered /me without `is_superuser` or `permissions`.
    server.use(
      http.get(api("/api/members/me"), () =>
        HttpResponse.json({
          user_id: 1,
          username: "alt",
          name: "Alt Bestand",
          member_id: null,
          is_staff: true,
        }),
      ),
    );
    const { captured } = renderHookWithApp(() => useMe());
    await waitFor(() => expect(captured.current?.data).toBeDefined());
    expect(captured.current?.data).toMatchObject({ is_superuser: false, permissions: [] });
  });

  it("does not fetch at all without a token", () => {
    localStorage.removeItem("kompass_token");
    const { captured } = renderHookWithApp(() => useMe(), undefined, { authenticated: false });
    expect(captured.current?.fetchStatus).toBe("idle");
    expect(captured.current?.data).toBeUndefined();
  });

  it("drops the Authorization header once the token is gone", async () => {
    // A refetch can outlive the token (logout mid-flight); the request must then
    // go out unauthenticated rather than sending "Bearer null".
    let seen: string | null = "unset";
    server.use(
      http.get(api("/api/members/me"), ({ request }) => {
        seen = request.headers.get("Authorization");
        return HttpResponse.json({
          user_id: 1,
          username: "x",
          name: "X",
          member_id: null,
          is_staff: true,
          is_superuser: false,
          permissions: [],
        });
      }),
    );
    const { captured } = renderHookWithApp(() => useMe());
    await waitFor(() => expect(captured.current?.data).toBeDefined());
    expect(seen).toBe("Bearer test-token");

    localStorage.removeItem("kompass_token");
    await act(async () => void (await captured.current!.refetch()));
    expect(seen).toBeNull();
  });

  it("surfaces a failing /me as an error rather than hanging", async () => {
    server.use(
      http.get(api("/api/members/me"), () => new HttpResponse(null, { status: 500 })),
    );
    const { captured } = renderHookWithApp(() => useMe());
    await waitFor(() => expect(captured.current?.error).toBeTruthy());
    expect(captured.current?.error?.message).toBe("Konnte aktuelle Anmeldung nicht laden.");
  });
});
