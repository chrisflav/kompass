import { useSyncExternalStore } from "react";

/**
 * Light and dark theme.
 *
 * The viewer chooses "system" (the default: whatever the OS asks for), "light"
 * or "dark", and the choice is remembered per browser. What the stylesheet sees
 * is only ever the resolved theme, on `<html data-theme>`: "system" is settled
 * here, so the CSS keys off one attribute and never asks the OS itself.
 *
 * index.html carries a copy of the first `applyTheme` that runs before the
 * first paint, so a dark-mode visitor is never flashed the light sheet while the
 * bundle loads. theme.test.ts checks that the two agree.
 */
export type ThemeChoice = "system" | "light" | "dark";
export type Theme = "light" | "dark";

export const THEME_STORAGE_KEY = "kompass_theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

/** The stored choice. Storage can be missing or refuse access (a private
 *  window, blocked site data); that reads as "no choice", i.e. the system's. */
export function readThemeChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Unreadable storage: fall through to the default.
  }
  return "system";
}

/** Remember a choice. "system" is the absence of one, so it clears the key. */
function storeThemeChoice(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Unwritable storage: the choice still holds for this page, just not beyond.
  }
}

function systemTheme(): Theme {
  return window.matchMedia(DARK_QUERY).matches ? "dark" : "light";
}

export function resolveTheme(choice: ThemeChoice, system: Theme = systemTheme()): Theme {
  return choice === "system" ? system : choice;
}

/** Put a theme on the document. `color-scheme` travels with it so form controls,
 *  scrollbars and the canvas before the stylesheet arrives match the palette. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
}

/* --- the current choice, shared by every switch on the page ------------- */

// Held in memory as well as in storage: with storage blocked the choice must
// still stick for as long as the page is open.
let current: ThemeChoice = readThemeChoice();
const listeners = new Set<() => void>();

function settle(choice: ThemeChoice) {
  current = choice;
  applyTheme(resolveTheme(choice));
  listeners.forEach((listener) => listener());
}

export function setThemeChoice(choice: ThemeChoice) {
  storeThemeChoice(choice);
  settle(choice);
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The viewer's choice, live, and a setter that applies and remembers it. */
export function useThemeChoice(): [ThemeChoice, (choice: ThemeChoice) => void] {
  const choice = useSyncExternalStore(subscribe, () => current);
  return [choice, setThemeChoice];
}

/**
 * Keep the document's theme current for the life of the page: follow the OS
 * while the choice is "system", and pick up a choice made in another tab.
 * Returns the matching cleanup.
 */
export function watchTheme(): () => void {
  settle(readThemeChoice());
  const media = window.matchMedia(DARK_QUERY);
  const onSystemChange = () => {
    if (current === "system") settle("system");
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key === THEME_STORAGE_KEY || e.key === null) settle(readThemeChoice());
  };
  media.addEventListener("change", onSystemChange);
  window.addEventListener("storage", onStorage);
  return () => {
    media.removeEventListener("change", onSystemChange);
    window.removeEventListener("storage", onStorage);
  };
}
