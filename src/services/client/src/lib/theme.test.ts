import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const STORAGE_KEY = "minder-theme";

function mockMatchMedia(matches: boolean) {
  const listeners: Array<() => void> = [];
  const mql = {
    matches,
    addEventListener: vi.fn((_: string, cb: () => void) => listeners.push(cb)),
  };
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => mql),
  );
  return { mql, fireChange: () => listeners.forEach((cb) => cb()) };
}

// jsdom (at least under this repo's current Node/jsdom combo) doesn't
// reliably expose a working `localStorage` global in the test environment --
// a real browser always has one, but here it's `undefined`. A tiny in-memory
// stub is simpler and more portable than chasing that environment quirk.
function stubLocalStorage() {
  const store = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, v),
    clear: () => store.clear(),
  });
}

beforeEach(() => {
  stubLocalStorage();
  document.documentElement.classList.remove("dark");
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getTheme", () => {
  it("defaults to 'system' when nothing is stored", async () => {
    mockMatchMedia(false);
    const { getTheme } = await import("./theme");
    expect(getTheme()).toBe("system");
  });

  it("returns a validly-stored preference", async () => {
    mockMatchMedia(false);
    localStorage.setItem(STORAGE_KEY, "dark");
    const { getTheme } = await import("./theme");
    expect(getTheme()).toBe("dark");
  });

  it("falls back to 'system' for a corrupted stored value", async () => {
    mockMatchMedia(false);
    localStorage.setItem(STORAGE_KEY, "purple");
    const { getTheme } = await import("./theme");
    expect(getTheme()).toBe("system");
  });
});

describe("setTheme", () => {
  it("applies the 'dark' class and persists the choice for theme='dark'", async () => {
    mockMatchMedia(false);
    const { setTheme, getTheme } = await import("./theme");

    setTheme("dark");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(getTheme()).toBe("dark");
  });

  it("removes the 'dark' class for theme='light' even if the OS prefers dark", async () => {
    mockMatchMedia(true); // OS says dark
    const { setTheme } = await import("./theme");

    setTheme("light");

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("for theme='system', mirrors the OS preference at the moment it's set", async () => {
    mockMatchMedia(true);
    const { setTheme } = await import("./theme");

    setTheme("system");

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});

describe("initTheme", () => {
  it("applies the currently-stored preference on call", async () => {
    mockMatchMedia(false);
    localStorage.setItem(STORAGE_KEY, "dark");
    const { initTheme } = await import("./theme");

    initTheme();

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("re-applies 'system' when the OS preference changes live", async () => {
    const { mql, fireChange } = mockMatchMedia(false);
    localStorage.setItem(STORAGE_KEY, "system");
    const { initTheme } = await import("./theme");
    initTheme();
    expect(document.documentElement.classList.contains("dark")).toBe(false);

    mql.matches = true; // OS flips to dark
    fireChange();

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("does NOT re-apply on an OS change while an explicit 'light'/'dark' choice is stored", async () => {
    const { mql, fireChange } = mockMatchMedia(false);
    localStorage.setItem(STORAGE_KEY, "light");
    const { initTheme } = await import("./theme");
    initTheme();

    mql.matches = true; // OS flips to dark, but the user pinned "light"
    fireChange();

    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
