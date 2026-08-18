import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "./ThemeToggle";

// jsdom (at least under this repo's current Node/jsdom combo) doesn't
// reliably expose a working `localStorage` global in tests -- see
// lib/theme.test.ts's identical stub for the full explanation.
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
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn() })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.documentElement.classList.remove("dark");
  cleanup();
});

describe("ThemeToggle", () => {
  it("starts on 'System' when no preference is stored", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /Theme: System/ })).toBeTruthy();
  });

  it("starts on the already-stored preference", () => {
    localStorage.setItem("minder-theme", "dark");
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: /Theme: Dark/ })).toBeTruthy();
  });

  it("cycles system -> light -> dark -> system on repeated clicks, persisting each step", () => {
    render(<ThemeToggle />);
    const button = screen.getByRole("button");

    fireEvent.click(button);
    expect(screen.getByRole("button", { name: /Theme: Light/ })).toBeTruthy();
    expect(localStorage.getItem("minder-theme")).toBe("light");

    fireEvent.click(button);
    expect(screen.getByRole("button", { name: /Theme: Dark/ })).toBeTruthy();
    expect(localStorage.getItem("minder-theme")).toBe("dark");

    fireEvent.click(button);
    expect(screen.getByRole("button", { name: /Theme: System/ })).toBeTruthy();
    expect(localStorage.getItem("minder-theme")).toBe("system");
  });

  it("applies the 'dark' class to <html> when cycled to dark", () => {
    render(<ThemeToggle />);
    fireEvent.click(screen.getByRole("button")); // -> light
    fireEvent.click(screen.getByRole("button")); // -> dark

    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
