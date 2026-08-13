import { describe, expect, it } from "vitest";

import { matchingSttLanguage } from "./stt";

const STT = { "tr-TR": "Turkish", "en-US": "English", "en-GB": "English (UK)" };

describe("matchingSttLanguage", () => {
  it("matches a bare TTS code to the STT BCP-47 locale by language prefix", () => {
    expect(matchingSttLanguage("tr", STT)).toBe("tr-TR");
  });

  it("returns the first STT locale that shares the language prefix", () => {
    // "en" prefixes both en-US and en-GB; Object.keys order → the first wins.
    expect(matchingSttLanguage("en", STT)).toBe("en-US");
  });

  it("returns null (not a guess) when no STT locale covers the language", () => {
    expect(matchingSttLanguage("de", STT)).toBeNull();
  });

  it("returns null for an empty STT map", () => {
    expect(matchingSttLanguage("tr", {})).toBeNull();
  });

  it("does not match on a partial prefix collision (e.g. 't' vs 'tr-TR')", () => {
    expect(matchingSttLanguage("t", STT)).toBeNull();
  });
});
