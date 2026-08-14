import { describe, expect, it } from "vitest";

import {
  Bundle,
  bundlesToStateExport,
  otherClaimants,
  outcomeSummary,
  parseBundleStateExport,
} from "./bundles";

describe("otherClaimants", () => {
  it("filters out the bundle's own name from its service's claimants", () => {
    // Found live: the API's `claimants` list always includes the bundle whose
    // card is being rendered, so "core"'s own services said "(also claimed by:
    // core)" -- a self-reference, not a real sharing signal.
    expect(
      otherClaimants({ name: "ollama", active: true, claimants: ["core"], image: null }, "core"),
    ).toEqual([]);
  });

  it("keeps other bundles' names", () => {
    expect(
      otherClaimants(
        { name: "ollama", active: true, claimants: ["chat", "inference", "rag"], image: null },
        "inference",
      ),
    ).toEqual(["chat", "rag"]);
  });

  it("drops falsy entries alongside the self-reference", () => {
    expect(
      otherClaimants(
        { name: "x", active: true, claimants: ["", "core", "rag"], image: null },
        "core",
      ),
    ).toEqual(["rag"]);
  });
});

describe("outcomeSummary", () => {
  it("summarizes a no-op result", () => {
    expect(
      outcomeSummary({
        started: [],
        already_running: [],
        pending_create: [],
        stopped: [],
        already_stopped: [],
        errors: [],
      }),
    ).toBe("no change needed.");
  });

  it("reports started services on enable", () => {
    expect(
      outcomeSummary({
        bundle: "rag",
        enabled: true,
        started: ["qdrant", "rag-pipeline"],
        already_running: [],
        pending_create: [],
        errors: [],
      }),
    ).toBe("started qdrant, rag-pipeline");
  });

  it("reports stopped services on disable", () => {
    expect(
      outcomeSummary({
        bundle: "rag",
        enabled: false,
        orphaned: [],
        stopped: ["qdrant"],
        already_stopped: [],
        absent: [],
        errors: [],
      }),
    ).toBe("stopped qdrant");
  });

  it("flags services needing a host converge", () => {
    expect(
      outcomeSummary({
        bundle: "rag",
        enabled: true,
        started: [],
        already_running: [],
        pending_create: ["graph-rag"],
        errors: [],
      }),
    ).toBe("graph-rag need a host converge (./setup.sh start/restart) to come up");
  });

  it("combines multiple parts and surfaces errors", () => {
    expect(
      outcomeSummary({
        bundle: "rag",
        enabled: true,
        started: ["qdrant"],
        already_running: [],
        pending_create: ["graph-rag"],
        errors: ["neo4j"],
      }),
    ).toBe(
      "started qdrant; graph-rag need a host converge (./setup.sh start/restart) to come up; errors on neo4j",
    );
  });
});

describe("bundlesToStateExport / parseBundleStateExport round-trip", () => {
  const bundles: Bundle[] = [
    { name: "core", core: true, enabled: true, claims: [], services: [] },
    { name: "rag", core: false, enabled: false, claims: [], services: [] },
  ];

  it("exports each bundle's name -> {enabled} shape", () => {
    expect(bundlesToStateExport(bundles)).toEqual({
      core: { enabled: true },
      rag: { enabled: false },
    });
  });

  it("re-parses its own export output unchanged", () => {
    const exported = bundlesToStateExport(bundles);
    expect(parseBundleStateExport(exported)).toEqual(exported);
  });

  it("rejects a non-object top level", () => {
    expect(() => parseBundleStateExport("nope")).toThrow();
    expect(() => parseBundleStateExport(null)).toThrow();
    expect(() => parseBundleStateExport([1, 2, 3])).toThrow();
  });

  it("rejects a bundle entry missing a boolean `enabled`", () => {
    expect(() => parseBundleStateExport({ core: {} })).toThrow('"core"');
    expect(() => parseBundleStateExport({ core: { enabled: "yes" } })).toThrow('"core"');
    expect(() => parseBundleStateExport({ core: null })).toThrow('"core"');
  });
});
