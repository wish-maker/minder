import { describe, expect, it } from "vitest";

import { badgeTone, confidenceBadgeColor } from "./ui";

describe("confidenceBadgeColor", () => {
  it("maps high confidence (>= 0.8) to the success tone", () => {
    expect(confidenceBadgeColor(0.8)).toBe(badgeTone.success);
    expect(confidenceBadgeColor(0.95)).toBe(badgeTone.success);
    expect(confidenceBadgeColor(1)).toBe(badgeTone.success);
  });

  it("maps mid confidence [0.5, 0.8) to the warn tone", () => {
    expect(confidenceBadgeColor(0.5)).toBe(badgeTone.warn);
    expect(confidenceBadgeColor(0.79)).toBe(badgeTone.warn);
  });

  it("maps low confidence (< 0.5) to the danger tone", () => {
    expect(confidenceBadgeColor(0.49)).toBe(badgeTone.danger);
    expect(confidenceBadgeColor(0)).toBe(badgeTone.danger);
  });

  it("uses distinct tones per bucket (boundaries don't collide)", () => {
    const tones = new Set([
      confidenceBadgeColor(0.9),
      confidenceBadgeColor(0.6),
      confidenceBadgeColor(0.1),
    ]);
    expect(tones.size).toBe(3);
  });
});
