/**
 * Manual light/dark/system theme control. Every page already ships `dark:`
 * Tailwind utilities, but until this module existed they were driven purely
 * by `@media (prefers-color-scheme: dark)` (see index.css's `@custom-variant
 * dark`) -- there was no way for a user to override their OS preference.
 *
 * "system" is the default for anyone who never touches the toggle, so
 * behavior is unchanged unless a preference is explicitly set.
 *
 * STORAGE_KEY's literal value is duplicated in index.html's inline
 * anti-flash script (it runs before any JS module loads, so it can't import
 * this file) -- keep the two in sync if this ever changes.
 */

export type Theme = "light" | "dark" | "system";

export const STORAGE_KEY = "minder-theme";

function systemPrefersDark(): boolean {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function isDarkFor(theme: Theme): boolean {
  return theme === "dark" || (theme === "system" && systemPrefersDark());
}

function applyClass(theme: Theme): void {
  document.documentElement.classList.toggle("dark", isDarkFor(theme));
}

/** Reads the persisted preference, defaulting to "system" for anyone who
 * hasn't chosen one yet (or has an invalid/corrupted stored value). Wrapped
 * in try/catch the same way index.html's inline anti-flash script is --
 * some browsers (Safari private mode, historically) throw on localStorage
 * access rather than just returning null, and a theme read should never be
 * the thing that crashes the app. */
export function getTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" || stored === "system"
      ? stored
      : "system";
  } catch {
    return "system";
  }
}

/** Persists the choice and immediately applies it. Applying still happens
 * even if persisting throws -- the choice just won't survive a reload. */
export function setTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    // Storage unavailable/full/blocked -- fall through, still apply below.
  }
  applyClass(theme);
}

let systemListenerAttached = false;

/** Call once at app startup: applies the current preference (redundant with
 * index.html's inline script on first paint, but needed for React's
 * lifetime -- e.g. a second tab changing the stored value doesn't reach
 * here, but the OS-preference-change listener below does) and, if the user
 * is on "system", keeps the applied class in sync as the OS preference
 * changes live without a page reload. */
export function initTheme(): void {
  applyClass(getTheme());

  if (systemListenerAttached) return;
  systemListenerAttached = true;
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (getTheme() === "system") applyClass("system");
  });
}
