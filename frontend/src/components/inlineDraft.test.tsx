import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../api/http";
import { InlineFlushError, useFlushRegistry, useInlineDraft } from "./inlineDraft";

interface Contact {
  prename: string;
  phone: string;
}

const SERVER_ROWS = [
  { id: 1, data: { prename: "Erika", phone: "0711 1" } },
  { id: 2, data: { prename: "Max", phone: "0711 2" } },
];

/**
 * Mount `useInlineDraft` with spy callbacks, capturing the flush function it
 * hands to its parent so a test can trigger the save itself.
 */
function setup(editing = true) {
  const create = vi.fn().mockResolvedValue(undefined);
  const update = vi.fn().mockResolvedValue(undefined);
  const remove = vi.fn().mockResolvedValue(undefined);
  const registered: { flush: () => Promise<void> } = { flush: async () => {} };
  const registerFlush = (fn: () => Promise<void>) => {
    registered.flush = fn;
  };

  const hook = renderHook(
    ({ editing: isEditing }) =>
      useInlineDraft<Contact>({
        serverRows: SERVER_ROWS,
        editing: isEditing,
        create,
        update,
        remove,
        registerFlush,
      }),
    { initialProps: { editing } },
  );

  const flush = () => act(async () => void (await registered.flush()));
  /** The raw flush, for tests that assert on the rejection itself. */
  const flushRaw = () => registered.flush();
  return { ...hook, create, update, remove, flush, flushRaw };
}

/** Last element; the project targets ES2020, so no `Array.prototype.at`. */
function last<T>(rows: T[]): T {
  return rows[rows.length - 1];
}

describe("useInlineDraft", () => {
  it("lists the server rows untouched before anything is staged", () => {
    const { result } = setup();
    expect(result.current.rows.map((r) => r.data.prename)).toEqual(["Erika", "Max"]);
    expect(result.current.rows.every((r) => r.id !== null)).toBe(true);
  });

  it("stages an added row without calling create", () => {
    const { result, create } = setup();
    act(() => result.current.addRow({ prename: "Neu", phone: "0711 9" }));
    expect(result.current.rows).toHaveLength(3);
    // A staged row has no server id yet; the UI keys per-row actions that need
    // one (e.g. uploading a certificate) off exactly that.
    expect(last(result.current.rows).id).toBeNull();
    expect(create).not.toHaveBeenCalled();
  });

  it("stages an edit without calling update", () => {
    const { result, update } = setup();
    act(() => result.current.setRow(result.current.rows[0], { prename: "Erika B.", phone: "x" }));
    expect(result.current.rows[0].data.prename).toBe("Erika B.");
    expect(update).not.toHaveBeenCalled();
  });

  it("hides a removed row without calling remove", () => {
    const { result, remove } = setup();
    act(() => result.current.removeRow(result.current.rows[0]));
    expect(result.current.rows.map((r) => r.data.prename)).toEqual(["Max"]);
    expect(remove).not.toHaveBeenCalled();
  });

  it("applies deletes, edits and creates when the parent saves", async () => {
    const { result, create, update, remove, flush } = setup();
    act(() => result.current.setRow(result.current.rows[1], { prename: "Maximilian", phone: "y" }));
    act(() => result.current.removeRow(result.current.rows[0]));
    act(() => result.current.addRow({ prename: "Neu", phone: "0711 9" }));

    await flush();

    expect(remove).toHaveBeenCalledWith(1);
    expect(update).toHaveBeenCalledWith(2, { prename: "Maximilian", phone: "y" });
    expect(create).toHaveBeenCalledWith({ prename: "Neu", phone: "0711 9" });
  });

  it("skips update for a row that was set back to its server values", async () => {
    const { result, update, flush } = setup();
    act(() => result.current.setRow(result.current.rows[0], { ...SERVER_ROWS[0].data }));
    await flush();
    expect(update).not.toHaveBeenCalled();
  });

  it("does not update a row that was also removed", async () => {
    const { result, update, remove, flush } = setup();
    act(() => result.current.setRow(result.current.rows[0], { prename: "Egal", phone: "z" }));
    act(() => result.current.removeRow(result.current.rows[0]));
    await flush();
    expect(remove).toHaveBeenCalledWith(1);
    expect(update).not.toHaveBeenCalled();
  });

  it("edits a staged row in place rather than creating two", async () => {
    const { result, create, flush } = setup();
    act(() => result.current.addRow({ prename: "Neu", phone: "" }));
    act(() => result.current.setRow(result.current.rows[2], { prename: "Neu", phone: "0711 9" }));
    await flush();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith({ prename: "Neu", phone: "0711 9" });
  });

  it("drops a staged row again without ever touching the server", async () => {
    const { result, create, remove, flush } = setup();
    act(() => result.current.addRow({ prename: "Versehen", phone: "" }));
    act(() => result.current.removeRow(result.current.rows[2]));
    expect(result.current.rows).toHaveLength(2);
    await flush();
    expect(create).not.toHaveBeenCalled();
    expect(remove).not.toHaveBeenCalled();
  });

  it("keeps staged rows when the parent save fails before flushing", () => {
    // The behaviour behind the withdrawn B4: a failed save leaves the drafts in
    // place, so the user can correct the problem and save again.
    const { result } = setup();
    act(() => result.current.addRow({ prename: "Neu", phone: "0711 9" }));
    expect(result.current.rows).toHaveLength(3);
    expect(last(result.current.rows).data.prename).toBe("Neu");
  });

  it("keeps staged rows when the flush itself throws", async () => {
    const { result, create, flushRaw } = setup();
    create.mockRejectedValueOnce(new Error("boom"));
    act(() => result.current.addRow({ prename: "Neu", phone: "0711 9" }));

    // The parent catches this and shows a toast; the drafts must survive so the
    // user can fix the problem and save again rather than retype everything.
    await act(async () => {
      await expect(flushRaw()).rejects.toThrow("boom");
    });
    expect(result.current.rows).toHaveLength(3);
    expect(last(result.current.rows).data.prename).toBe("Neu");
  });

  it("discards staged rows when edit mode is left", () => {
    const { result, rerender } = setup(true);
    act(() => result.current.addRow({ prename: "Neu", phone: "0711 9" }));
    expect(result.current.rows).toHaveLength(3);
    rerender({ editing: false });
    expect(result.current.rows).toHaveLength(2);
  });
});

describe("useFlushRegistry", () => {
  it("runs every registered inline's flush", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    const contacts = vi.fn().mockResolvedValue(undefined);
    const documents = vi.fn().mockResolvedValue(undefined);
    act(() => {
      result.current.getRegistrar("contacts")(contacts);
      result.current.getRegistrar("documents")(documents);
    });
    await act(async () => void (await result.current.runFlushes()));
    expect(contacts).toHaveBeenCalled();
    expect(documents).toHaveBeenCalled();
  });

  it("wraps an inline failure so the parent cannot mis-route its field errors", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    const failing = vi
      .fn()
      .mockRejectedValue(new ApiError(422, { errors: { phone_number: ["Pflichtfeld."] } }));
    act(() => result.current.getRegistrar("contacts")(failing));

    // Deliberately NOT an ApiError: a parent's catch maps `ApiError.fieldErrors`
    // onto its own fields, which would put an emergency contact's phone error on
    // the member's phone field, in a different tab.
    const error = await result.current.runFlushes().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(InlineFlushError);
    expect(error).not.toBeInstanceOf(ApiError);
    expect((error as Error).message).toContain("Pflichtfeld.");
  });

  it("stops at the first failing inline", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    const failing = vi.fn().mockRejectedValue(new Error("boom"));
    const later = vi.fn().mockResolvedValue(undefined);
    act(() => {
      result.current.getRegistrar("a")(failing);
      result.current.getRegistrar("b")(later);
    });
    await expect(result.current.runFlushes()).rejects.toBeInstanceOf(InlineFlushError);
    expect(later).not.toHaveBeenCalled();
  });

  it("keeps a registrar stable so re-registering replaces rather than duplicates", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    const first = result.current.getRegistrar("contacts");
    const second = result.current.getRegistrar("contacts");
    expect(first).toBe(second);

    const fn = vi.fn().mockResolvedValue(undefined);
    act(() => {
      first(fn);
      second(fn);
    });
    await act(async () => void (await result.current.runFlushes()));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});

describe("InlineFlushError message", () => {
  it("describes a thrown value that is not an Error at all", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    // A rejected promise can carry anything; the message must still read.
    act(() => result.current.getRegistrar("x")(() => Promise.reject("kaputt")));
    await expect(result.current.runFlushes()).rejects.toThrow(
      "Ein verknüpfter Eintrag konnte nicht gespeichert werden: kaputt",
    );
  });

  it("uses a plain Error's message", async () => {
    const { result } = renderHook(() => useFlushRegistry());
    act(() => result.current.getRegistrar("x")(() => Promise.reject(new Error("Netzwerk weg"))));
    await expect(result.current.runFlushes()).rejects.toThrow(
      "Ein verknüpfter Eintrag konnte nicht gespeichert werden: Netzwerk weg",
    );
  });
});
