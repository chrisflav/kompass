import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../api/http";

/**
 * Raised when a related-object inline fails to save during the parent form's
 * Save. It is deliberately NOT an `ApiError`: a parent's submit catch routes
 * `ApiError.fieldErrors` onto its OWN fields, and an inline's field names (e.g.
 * an emergency contact's `phone_number`) would otherwise be shown on the parent
 * record's like-named field in the wrong tab. Being a plain Error, it skips that
 * routing and only surfaces as a toast, naming the failing section.
 */
export class InlineFlushError extends Error {
  constructor(cause: unknown) {
    const detail =
      cause instanceof ApiError && Object.keys(cause.fieldErrors).length
        ? Object.values(cause.fieldErrors).flat().join(" ")
        : cause instanceof Error
          ? cause.message
          : String(cause);
    super(`Ein verknüpfter Eintrag konnte nicht gespeichert werden: ${detail}`);
    this.name = "InlineFlushError";
  }
}

/**
 * Parent-side coordination for deferred inline editors. Each inline registers a
 * `flush` (keyed) via `getRegistrar(key)`; the parent form's Save calls
 * `runFlushes()` after persisting its own fields, so inline changes are applied
 * together with the main Save rather than per-inline.
 */
export function useFlushRegistry() {
  const flushers = useRef(new Map<string, () => Promise<void>>());
  const registrars = useRef<Record<string, (fn: () => Promise<void>) => void>>({});

  const getRegistrar = useCallback((key: string) => {
    if (!registrars.current[key]) {
      registrars.current[key] = (fn) => {
        flushers.current.set(key, fn);
      };
    }
    return registrars.current[key];
  }, []);

  const runFlushes = useCallback(async () => {
    for (const flush of flushers.current.values()) {
      try {
        await flush();
      } catch (e) {
        // Wrap so the parent's catch treats it as a section-level failure
        // (toast) rather than mapping the inline's field errors onto itself.
        throw new InlineFlushError(e);
      }
    }
  }, []);

  return { getRegistrar, runFlushes };
}

/** A row in an inline editor's working set. */
export interface DraftRow<T> {
  /** Stable React key (server id as string, or a `new-N` token). */
  key: string;
  /** Server id, or null for a row that has not been created yet. */
  id: number | null;
  /** Current (possibly edited) field values. */
  data: T;
}

/**
 * Stages create / edit / delete for a related-object inline **without** saving
 * immediately: existing rows are editable in place, new rows are added to the
 * working set, deletions are marked, and everything is applied only when the
 * parent form's Save runs `flush()` (registered via `registerFlush`). Leaving
 * edit mode discards the staged changes.
 */
export function useInlineDraft<T>({
  serverRows,
  editing,
  create,
  update,
  remove,
  dirty = (a, b) => JSON.stringify(a) !== JSON.stringify(b),
  registerFlush,
}: {
  serverRows: { id: number; data: T }[];
  editing: boolean;
  create: (data: T) => Promise<unknown>;
  update: (id: number, data: T) => Promise<unknown>;
  remove: (id: number) => Promise<unknown>;
  /** Whether an edited existing row differs from its server value (skip clean rows). */
  dirty?: (current: T, original: T) => boolean;
  /** Registers this editor's flush fn with the parent form (stable callback). */
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const [edits, setEdits] = useState<Record<number, T>>({});
  const [pendingNew, setPendingNew] = useState<{ key: string; data: T }[]>([]);
  const [deleted, setDeleted] = useState<Set<number>>(() => new Set());
  const tempSeq = useRef(0);

  // Discard the working set whenever we leave edit mode (Cancel or after Save).
  useEffect(() => {
    if (!editing) {
      setEdits({});
      setPendingNew([]);
      setDeleted(new Set());
    }
  }, [editing]);

  const originalById = useMemo(() => {
    const m = new Map<number, T>();
    serverRows.forEach((r) => m.set(r.id, r.data));
    return m;
  }, [serverRows]);

  const rows: DraftRow<T>[] = useMemo(() => {
    const existing = serverRows
      .filter((r) => !deleted.has(r.id))
      .map((r) => ({ key: String(r.id), id: r.id, data: edits[r.id] ?? r.data }));
    const created = pendingNew.map((n) => ({ key: n.key, id: null, data: n.data }));
    return [...existing, ...created];
  }, [serverRows, deleted, edits, pendingNew]);

  const setRow = useCallback((row: DraftRow<T>, data: T) => {
    if (row.id === null) {
      setPendingNew((prev) => prev.map((n) => (n.key === row.key ? { ...n, data } : n)));
    } else {
      const id = row.id;
      setEdits((prev) => ({ ...prev, [id]: data }));
    }
  }, []);

  const removeRow = useCallback((row: DraftRow<T>) => {
    if (row.id === null) {
      setPendingNew((prev) => prev.filter((n) => n.key !== row.key));
    } else {
      const id = row.id;
      setDeleted((prev) => new Set(prev).add(id));
      setEdits((prev) => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }
  }, []);

  const addRow = useCallback((data: T) => {
    tempSeq.current += 1;
    setPendingNew((prev) => [...prev, { key: `new-${tempSeq.current}`, data }]);
  }, []);

  // Reassigned every render so it always closes over the latest staged state;
  // the registered wrapper is stable and just calls the current impl.
  const flushImpl = useRef<() => Promise<void>>(async () => {});
  flushImpl.current = async () => {
    for (const id of deleted) await remove(id);
    for (const [idStr, data] of Object.entries(edits)) {
      const id = Number(idStr);
      if (deleted.has(id)) continue;
      const orig = originalById.get(id);
      if (orig === undefined || dirty(data, orig)) await update(id, data);
    }
    for (const n of pendingNew) await create(n.data);
  };
  const flush = useCallback(() => flushImpl.current(), []);
  useEffect(() => registerFlush(flush), [registerFlush, flush]);

  return { rows, setRow, removeRow, addRow };
}
