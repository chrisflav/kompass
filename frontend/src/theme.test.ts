import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import indexHtml from "../index.html?raw";
import {
  applyTheme,
  readThemeChoice,
  resolveTheme,
  setThemeChoice,
  THEME_STORAGE_KEY,
  useThemeChoice,
  watchTheme,
  type ThemeChoice,
} from "./theme";

/* --- a system preference the test can flip -------------------------------
 *
 * jsdom has no `matchMedia`; setup.ts stubs one that never matches and never
 * fires. These tests need an OS that prefers dark, and one that changes its
 * mind, so they swap in a query list of their own.
 */
const realMatchMedia = window.matchMedia;

function fakeSystem(dark: boolean) {
  const listeners = new Set<() => void>();
  const list = {
    matches: dark,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  };
  window.matchMedia = (() => list) as unknown as typeof window.matchMedia;
  return {
    listeners,
    /** The OS switches its appearance, as the user toggling it would. */
    flip(nowDark: boolean) {
      list.matches = nowDark;
      listeners.forEach((listener) => listener());
    },
  };
}

const root = document.documentElement;

beforeEach(() => fakeSystem(false));

afterEach(() => {
  // The choice lives in module state too; put it back to the default.
  act(() => setThemeChoice("system"));
  window.matchMedia = realMatchMedia;
  delete root.dataset.theme;
  root.style.colorScheme = "";
});

describe("the stored choice", () => {
  it("defaults to the system when nothing is stored", () => {
    expect(readThemeChoice()).toBe("system");
  });

  it("reads a stored light or dark choice back", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    expect(readThemeChoice()).toBe("dark");
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    expect(readThemeChoice()).toBe("light");
  });

  it("treats anything else in storage as no choice", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "sepia");
    expect(readThemeChoice()).toBe("system");
  });

  it("falls back to the system when storage refuses to be read", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    expect(readThemeChoice()).toBe("system");
  });
});

describe("resolving and applying", () => {
  it("settles System into whatever the OS prefers", () => {
    expect(resolveTheme("system", "dark")).toBe("dark");
    expect(resolveTheme("system", "light")).toBe("light");
    fakeSystem(true);
    expect(resolveTheme("system")).toBe("dark");
  });

  it("lets an explicit choice override the OS", () => {
    fakeSystem(true);
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark", "light")).toBe("dark");
  });

  it("puts the theme and the matching colour scheme on the document", () => {
    applyTheme("dark");
    expect(root.dataset.theme).toBe("dark");
    expect(root.style.colorScheme).toBe("dark");
    applyTheme("light");
    expect(root.dataset.theme).toBe("light");
    expect(root.style.colorScheme).toBe("light");
  });
});

describe("choosing", () => {
  it("applies and remembers an explicit choice", () => {
    setThemeChoice("dark");
    expect(root.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("forgets the stored choice when going back to System", () => {
    fakeSystem(true);
    setThemeChoice("light");
    expect(root.dataset.theme).toBe("light");
    setThemeChoice("system");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(root.dataset.theme).toBe("dark");
  });

  it("still applies a choice for this page when storage refuses to write", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    const { result } = renderHook(() => useThemeChoice());
    act(() => result.current[1]("dark"));
    expect(result.current[0]).toBe("dark");
    expect(root.dataset.theme).toBe("dark");
  });

  it("tells every subscriber about a new choice", () => {
    const a = renderHook(() => useThemeChoice());
    const b = renderHook(() => useThemeChoice());
    expect(a.result.current[0]).toBe("system");
    act(() => a.result.current[1]("light"));
    expect(b.result.current[0]).toBe("light");
  });
});

describe("watching", () => {
  it("follows the OS live while the choice is System", () => {
    const system = fakeSystem(false);
    const stop = watchTheme();
    expect(root.dataset.theme).toBe("light");

    act(() => system.flip(true));
    expect(root.dataset.theme).toBe("dark");
    act(() => system.flip(false));
    expect(root.dataset.theme).toBe("light");
    stop();
    expect(system.listeners.size).toBe(0);
  });

  it("holds an explicit choice whatever the OS does", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    const system = fakeSystem(false);
    const stop = watchTheme();
    act(() => system.flip(true));
    expect(root.dataset.theme).toBe("light");
    stop();
  });

  it("picks up a choice made in another tab", () => {
    const stop = watchTheme();
    const { result } = renderHook(() => useThemeChoice());

    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY }));
    });
    expect(result.current[0]).toBe("dark");
    expect(root.dataset.theme).toBe("dark");

    // Another tab clearing all storage reads as going back to System.
    localStorage.clear();
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: null }));
    });
    expect(result.current[0]).toBe("system");

    // Someone else's key is none of the theme's business.
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "kompass_token" }));
    });
    expect(result.current[0]).toBe("system");
    stop();
  });
});

/* --- the copy in index.html ----------------------------------------------
 *
 * The page settles the theme in an inline script before the bundle arrives,
 * and the bundle then takes over. If the two disagreed, the page would flip
 * theme the moment the app booted — the very flash the script exists to avoid.
 */
describe("the pre-paint script in index.html", () => {
  const script = /<script>([\s\S]*?)<\/script>/.exec(indexHtml)![1];

  function runScript() {
    delete root.dataset.theme;
    root.style.colorScheme = "";
    new Function(script)();
    return { theme: root.dataset.theme, scheme: root.style.colorScheme };
  }

  const stored: (ThemeChoice | "sepia" | null)[] = [null, "light", "dark", "sepia"];
  for (const value of stored) {
    for (const dark of [false, true]) {
      const os = dark ? "dark" : "light";
      it(`agrees with theme.ts for ${value ?? "nothing"} stored, OS ${os}`, () => {
        if (value) localStorage.setItem(THEME_STORAGE_KEY, value);
        fakeSystem(dark);
        const expected = resolveTheme(readThemeChoice());
        expect(runScript()).toEqual({ theme: expected, scheme: expected });
      });
    }
  }

  it("still follows the OS when storage refuses to be read", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    fakeSystem(true);
    expect(runScript()).toEqual({ theme: "dark", scheme: "dark" });
  });
});
