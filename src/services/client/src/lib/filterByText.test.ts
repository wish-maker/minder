import { describe, expect, it } from "vitest";

import { filterByText } from "./filterByText";

interface Item {
  name: string;
  tag: string;
}

const items: Item[] = [
  { name: "Alpha docs", tag: "prod" },
  { name: "Beta notes", tag: "staging" },
  { name: "Gamma", tag: "prod" },
];

const byNameTag = (i: Item) => [i.name, i.tag];

describe("filterByText", () => {
  it("returns a copy of the whole list for a blank query", () => {
    const out = filterByText(items, "", byNameTag);
    expect(out).toEqual(items);
    expect(out).not.toBe(items); // new array, not the same reference
  });

  it("treats whitespace-only as blank", () => {
    expect(filterByText(items, "   ", byNameTag)).toHaveLength(3);
  });

  it("matches case-insensitively on any provided field", () => {
    expect(filterByText(items, "ALPHA", byNameTag).map((i) => i.name)).toEqual([
      "Alpha docs",
    ]);
    // matches on the tag field too
    expect(filterByText(items, "prod", byNameTag).map((i) => i.name)).toEqual([
      "Alpha docs",
      "Gamma",
    ]);
  });

  it("matches on a substring, not just a prefix", () => {
    expect(filterByText(items, "otes", byNameTag).map((i) => i.name)).toEqual([
      "Beta notes",
    ]);
  });

  it("returns an empty list when nothing matches", () => {
    expect(filterByText(items, "zzz", byNameTag)).toEqual([]);
  });
});
