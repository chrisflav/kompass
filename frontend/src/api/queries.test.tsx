import { QueryClient } from "@tanstack/react-query";
import { screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { useApiMutation } from "./hooks";
import { queryKeys, useMembers } from "./queries";
import { api, http, HttpResponse, server } from "../test/server";
import { renderWithApp } from "../test/utils";

/** Counts the requests to `path` while answering them with `body`. */
function counting(path: string, body: unknown[]) {
  const calls = { count: 0 };
  server.use(
    http.get(api(path), () => {
      calls.count += 1;
      return HttpResponse.json(body);
    }),
  );
  return calls;
}

function MembersReader({ label }: { label: string }) {
  const members = useMembers();
  return <p>{members.data ? `${label}: ${members.data.length}` : `${label}: …`}</p>;
}

/** A page that reads the members, can mount a second reader later (another
 *  page navigated to) and can save something that invalidates the list. */
function Harness() {
  const [later, setLater] = useState(false);
  const save = useApiMutation(async () => null, { invalidate: [queryKeys.members()] });
  const touch = useApiMutation(async () => null, { markStale: [queryKeys.members()] });
  return (
    <>
      <MembersReader label="erste" />
      <MembersReader label="zweite" />
      {later && <MembersReader label="später" />}
      <button type="button" onClick={() => setLater(true)}>
        weiter
      </button>
      <button type="button" onClick={() => save.mutate(undefined)}>
        speichern
      </button>
      <button type="button" onClick={() => touch.mutate(undefined)}>
        nebenbei
      </button>
    </>
  );
}

describe("shared reference lists", () => {
  it("serves every reader of a list from one request", async () => {
    const calls = counting("/api/members/", [{ id: 1, name: "Anna" }]);
    renderWithApp(<Harness />);
    expect(await screen.findByText("erste: 1")).toBeInTheDocument();
    expect(screen.getByText("zweite: 1")).toBeInTheDocument();
    expect(calls.count).toBe(1);
  });

  it("does not refetch a fresh list for the next page that reads it", async () => {
    const calls = counting("/api/members/", [{ id: 1, name: "Anna" }]);
    const { user } = renderWithApp(<Harness />);
    await screen.findByText("erste: 1");

    await user.click(screen.getByRole("button", { name: "weiter" }));
    expect(screen.getByText("später: 1")).toBeInTheDocument();
    expect(calls.count).toBe(1);
  });

  it("refetches once a mutation invalidates the list", async () => {
    const calls = counting("/api/members/", [{ id: 1, name: "Anna" }]);
    const { user } = renderWithApp(<Harness />);
    await screen.findByText("erste: 1");

    await user.click(screen.getByRole("button", { name: "speichern" }));
    await waitFor(() => expect(calls.count).toBe(2));
  });

  it("only marks a list stale for `markStale`, refetching it for the next reader", async () => {
    const calls = counting("/api/members/", [{ id: 1, name: "Anna" }]);
    const { user } = renderWithApp(<Harness />);
    await screen.findByText("erste: 1");

    await user.click(screen.getByRole("button", { name: "nebenbei" }));
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls.count).toBe(1);

    await user.click(screen.getByRole("button", { name: "weiter" }));
    await waitFor(() => expect(calls.count).toBe(2));
  });
});

describe("message query keys", () => {
  it("invalidates both list windows, and the details, with the messages key", async () => {
    const qc = new QueryClient();
    const recent = queryKeys.messageList("2025-10-12");
    const all = queryKeys.messageList(null);
    const detail = ["mailer", "messages", 4];
    const addresses = queryKeys.emailAddresses();
    for (const key of [recent, all, detail, addresses]) qc.setQueryData(key, []);
    expect(recent).not.toEqual(all);

    await qc.invalidateQueries({ queryKey: queryKeys.messages() });

    expect(qc.getQueryState(recent)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(all)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(detail)?.isInvalidated).toBe(true);
    expect(qc.getQueryState(addresses)?.isInvalidated).toBe(false);
  });
});
