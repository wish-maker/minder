import { describe, expect, it } from "vitest";

import {
  pickDefaultRewriteModel,
  usableRewriteModels,
  type RewriteModelInfo,
} from "./rewriteModel";

const MODELS: RewriteModelInfo[] = [
  { id: "granite3-moe:latest", status: "ready" },
  { id: "nomic-embed-text:latest", status: "ready" },
  { id: "llama3.2-vision:latest", status: "ready" },
  { id: "llama3.2:latest", status: "ready" },
  { id: "gemma4:26b", status: "ready" },
  { id: "dolphin-mistral:latest", status: "loading" },
];

describe("usableRewriteModels", () => {
  it("excludes embedding-only models by name", () => {
    const ids = usableRewriteModels(MODELS).map((m) => m.id);
    expect(ids).not.toContain("nomic-embed-text:latest");
  });

  it("excludes models that aren't ready", () => {
    const ids = usableRewriteModels(MODELS).map((m) => m.id);
    expect(ids).not.toContain("dolphin-mistral:latest");
  });

  it("keeps every ready, non-embedding model", () => {
    const ids = usableRewriteModels(MODELS).map((m) => m.id);
    expect(ids).toEqual([
      "granite3-moe:latest",
      "llama3.2-vision:latest",
      "llama3.2:latest",
      "gemma4:26b",
    ]);
  });

  it("returns an empty list when nothing is usable", () => {
    expect(usableRewriteModels([{ id: "x:latest", status: "loading" }])).toEqual(
      [],
    );
  });
});

describe("pickDefaultRewriteModel", () => {
  it("prefers gemma4 over llama3.2 and whatever sorts first", () => {
    // granite3-moe sorts first in MODELS but must never win (ignored Turkish
    // instructions, replied in English -- #597); llama3.2 is a real model
    // but must lose to gemma4 -- found live: llama3.2 often answered the
    // input conversationally instead of rewriting it, and leaked English/
    // German/Portuguese words, while gemma4:26b reliably rewrote correctly
    // across all 4 regional styles (this fixup's regression test).
    expect(pickDefaultRewriteModel(MODELS)).toBe("gemma4:26b");
  });

  it("falls back to llama3.2 when gemma4 isn't available", () => {
    const models: RewriteModelInfo[] = [
      { id: "granite3-moe:latest", status: "ready" },
      { id: "llama3.2:latest", status: "ready" },
    ];
    expect(pickDefaultRewriteModel(models)).toBe("llama3.2:latest");
  });

  it("does not match a same-family variant like llama3.2-vision", () => {
    const models: RewriteModelInfo[] = [
      { id: "some-other-model:latest", status: "ready" },
      { id: "llama3.2-vision:latest", status: "ready" },
    ];
    // "llama3.2-vision:latest" must not satisfy startsWith("llama3.2:") --
    // if it did, it would win here despite sorting second; instead the
    // first usable model (by list order) is the correct fallback.
    expect(pickDefaultRewriteModel(models)).toBe("some-other-model:latest");
  });

  it("falls back to the first usable model when no preferred family is present", () => {
    const models: RewriteModelInfo[] = [
      { id: "mistral-nemo:12b", status: "ready" },
      { id: "qwen3:30b", status: "ready" },
    ];
    expect(pickDefaultRewriteModel(models)).toBe("mistral-nemo:12b");
  });

  it("returns an empty string when nothing is usable", () => {
    expect(pickDefaultRewriteModel([])).toBe("");
    expect(
      pickDefaultRewriteModel([{ id: "nomic-embed-text:latest", status: "ready" }]),
    ).toBe("");
  });
});
