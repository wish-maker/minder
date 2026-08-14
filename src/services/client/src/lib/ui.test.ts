import { describe, expect, it } from "vitest";

import { badgeTone, confidenceBadgeColor, sectionLabelClass, statusClass } from "./ui";

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

describe("sectionLabelClass", () => {
  it("does not use the gray-400/gray-500 pairing an axe-core audit found fails WCAG AA contrast (#509)", () => {
    expect(sectionLabelClass).not.toContain("text-gray-400 dark:text-gray-500");
    expect(sectionLabelClass).toContain("text-gray-500 dark:text-gray-400");
  });
});

describe("statusClass", () => {
  it("has a dark-mode-specific error color -- plain text-red-600 with no dark variant failed WCAG AA contrast in dark mode per an axe-core audit (#509)", () => {
    expect(statusClass(true)).toContain("dark:text-red-400");
  });
});
