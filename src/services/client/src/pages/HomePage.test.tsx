import { describe, expect, it } from "vitest";

import { primaryAction, type HomeStats } from "./HomePage";

function stats(overrides: Partial<HomeStats> = {}): HomeStats {
  return {
    kbCount: 0,
    pipelineCount: 0,
    bundlesEnabled: 0,
    bundlesTotal: 0,
    modelCount: 0,
    ...overrides,
  };
}

describe("primaryAction", () => {
  it("suggests creating a knowledge base when stats haven't loaded yet", () => {
    expect(primaryAction(null).to).toBe("/rag");
  });

  it("suggests creating a knowledge base when none exist", () => {
    const action = primaryAction(stats({ kbCount: 0, pipelineCount: 5 }));
    expect(action.to).toBe("/rag");
    expect(action.title).toBe("Create your first knowledge base");
  });

  it("suggests building a pipeline once a KB exists but no pipeline does", () => {
    const action = primaryAction(stats({ kbCount: 1, pipelineCount: 0 }));
    expect(action.to).toBe("/rag/pipelines");
    expect(action.title).toBe("Build a pipeline");
    expect(action.body).toContain("1 knowledge base ready"); // singular, not "1 knowledge bases"
  });

  it("pluralizes the knowledge-base count correctly in the pipeline suggestion", () => {
    const action = primaryAction(stats({ kbCount: 3, pipelineCount: 0 }));
    expect(action.body).toContain("3 knowledge bases ready");
  });

  it("suggests asking a question once both a KB and a pipeline exist", () => {
    const action = primaryAction(stats({ kbCount: 2, pipelineCount: 1 }));
    expect(action.to).toBe("/rag/pipelines");
    expect(action.title).toBe("Ask a question");
    expect(action.body).toContain("1 pipeline "); // singular, not "1 pipelines"
  });

  it("pluralizes the pipeline count correctly in the ask-a-question suggestion", () => {
    const action = primaryAction(stats({ kbCount: 2, pipelineCount: 4 }));
    expect(action.body).toContain("4 pipelines ");
  });
});
