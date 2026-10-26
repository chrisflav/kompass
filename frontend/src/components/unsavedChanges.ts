import { useEffect } from "react";

/* --- unsaved input -------------------------------------------------------
 *
 * A form with unsaved input asks before the tab is closed or reloaded. Leaving
 * on purpose — signing out, say — asks in the app's own words first, and the
 * browser's prompt must then stay quiet rather than ask a second time.
 */
let unsaved = 0;
let leaving = false;

/** Warns before the tab is closed or reloaded while `dirty` holds. */
export function useUnloadWarning(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    unsaved += 1;
    const warn = (e: BeforeUnloadEvent) => {
      if (!leaving) e.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => {
      unsaved -= 1;
      window.removeEventListener("beforeunload", warn);
    };
  }, [dirty]);
}

/** Whether a mounted form holds input that leaving the page would lose. */
export function hasUnsavedChanges(): boolean {
  return unsaved > 0;
}

/** Leaves the page without the browser's prompt; the caller already asked. */
export function leavePage(url: string) {
  leaving = true;
  window.location.assign(url);
}
