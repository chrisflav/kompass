import { Component, type ReactNode } from "react";

import { Button } from "./ui";

/** When this tab last reloaded to pick up a new build (epoch ms). */
const RELOADED_AT = "kompass_chunk_reload";

/** A second failure within this window means the reload did not help, so the
 *  page stops reloading itself and shows {@link ChunkBoundary}'s state instead.
 *  A later deploy, minutes on, is allowed its own reload. */
const RELOAD_WINDOW_MS = 10_000;

/**
 * Reload the page to fetch the current build, unless this tab already did so
 * within {@link RELOAD_WINDOW_MS}. Returns whether it reloaded.
 *
 * Vite's chunk filenames carry a content hash, so after a deploy the scripts an
 * open tab still refers to are gone. A reload fetches the new index.html and,
 * with it, the new names. Storage that refuses access (a private window, blocked
 * site data) counts as a spent guard: better a reload button than a loop.
 */
export function reloadOnce(reload: () => void = () => window.location.reload()): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOADED_AT) ?? 0);
    const now = Date.now();
    if (now - last < RELOAD_WINDOW_MS) return false;
    sessionStorage.setItem(RELOADED_AT, String(now));
  } catch {
    return false;
  }
  reload();
  return true;
}

/**
 * Handler for Vite's `vite:preloadError`, fired when a lazily imported chunk
 * fails to load. Reloads once and swallows the error; once the guard is spent
 * the error goes on to the nearest {@link ChunkBoundary}.
 */
export function handlePreloadError(event: Event, reload?: () => void) {
  if (reloadOnce(reload)) event.preventDefault();
}

/**
 * Catches a lazily loaded part of the app that failed to arrive. React.lazy
 * caches the rejection, so without this the whole tree unmounts to a blank
 * page; with it, the reader gets a way back to a working build.
 */
export class ChunkBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="error state" role="alert">
        <p>Neue Version verfügbar – neu laden, um weiterzumachen.</p>
        <Button onClick={() => window.location.reload()}>Neu laden</Button>
      </div>
    );
  }
}
