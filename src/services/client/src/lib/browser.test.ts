import { afterEach, describe, expect, it, vi } from "vitest";

import { copyText, randomId } from "./browser";

describe("randomId", () => {
  it("returns a v4-format UUID", () => {
    expect(randomId()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("returns distinct values across calls", () => {
    expect(randomId()).not.toBe(randomId());
  });
});

describe("copyText", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses navigator.clipboard when available and reports success", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await expect(copyText("hello")).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("returns false (never throws) when the clipboard API is unavailable", async () => {
    // Plain-HTTP / non-secure context: navigator.clipboard is undefined and jsdom
    // doesn't implement execCommand — copyText must degrade to false, not reject.
    vi.stubGlobal("navigator", {});
    await expect(copyText("hello")).resolves.toBe(false);
  });
});
