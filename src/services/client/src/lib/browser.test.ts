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

describe("randomId fallbacks (non-secure context: no crypto.randomUUID)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("falls back to crypto.getRandomValues when randomUUID is unavailable", () => {
    const getRandomValues = vi.fn((arr: Uint8Array) => arr.fill(0xab));
    vi.stubGlobal("crypto", { getRandomValues });

    const id = randomId();

    expect(getRandomValues).toHaveBeenCalledOnce();
    expect(id).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
  });

  it("falls back to Math.random when crypto is entirely unavailable", () => {
    vi.stubGlobal("crypto", undefined);

    expect(randomId()).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
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

  it("falls through to the legacy execCommand path when clipboard.writeText rejects", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });

    // jsdom doesn't implement execCommand either, so this still degrades to
    // false overall -- the point is exercising the first try/catch's
    // fall-through, not the final outcome.
    await expect(copyText("hello")).resolves.toBe(false);
    expect(writeText).toHaveBeenCalledWith("hello");
  });
});
