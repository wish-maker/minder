import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../lib/api";
import {
  AutoRouterStatsCard,
  CreatePipelineForm,
  PipelineCard,
  QueryPanel,
  QueryResultCard,
  RagPipelinesPage,
  RetrievalMethodsReference,
  type Capabilities,
  type KnowledgeBase,
  type QueryResponse,
  type RagPipeline,
} from "./RagPipelinesPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    apiFetch: (...args: unknown[]) => apiFetch(...args),
  };
});
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ token: "test-token" }),
}));
vi.mock("../components/ConfirmDialog", () => ({
  useConfirm: () => ({ confirm: vi.fn(), dialog: null }),
}));

afterEach(() => {
  apiFetch.mockReset();
  cleanup();
});

// AutoRouterStatsCard is a pure presentational component (GET /v1/rag/decision-stats
// analytics, #707) — test its state branches directly by prop, no page mount needed.
describe("AutoRouterStatsCard", () => {
  it("renders nothing when stats are absent (deploy-skew graceful null)", () => {
    const { container } = render(<AutoRouterStatsCard stats={null} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when the auto engine is unavailable", () => {
    const { container } = render(
      <AutoRouterStatsCard
        stats={{
          available: false,
          total_decisions: 0,
          strategy_distribution: {},
          complexity_distribution: {},
          avg_confidence: null,
        }}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the empty note when available but no auto queries ran yet", () => {
    render(
      <AutoRouterStatsCard
        stats={{
          available: true,
          total_decisions: 0,
          strategy_distribution: {},
          complexity_distribution: {},
          avg_confidence: null,
        }}
      />,
    );
    expect(screen.getByText(/No/i)).toBeTruthy();
    expect(screen.getByText(/0 decisions recorded/i)).toBeTruthy();
  });

  it("renders the distributions and avg confidence when populated", () => {
    render(
      <AutoRouterStatsCard
        stats={{
          available: true,
          total_decisions: 3,
          strategy_distribution: { hybrid: 2, standard: 1 },
          complexity_distribution: { moderate: 2, simple: 1 },
          avg_confidence: 0.8,
        }}
      />,
    );
    expect(screen.getByText(/3 decisions recorded/i)).toBeTruthy();
    expect(screen.getByText("hybrid: 2")).toBeTruthy();
    expect(screen.getByText("standard: 1")).toBeTruthy();
    expect(screen.getByText("moderate: 2")).toBeTruthy();
    // avg_confidence 0.8 → "80%"
    expect(screen.getByText("80%")).toBeTruthy();
  });
});

describe("RetrievalMethodsReference", () => {
  it("lists every retrieval method and add-on", () => {
    render(<RetrievalMethodsReference />);
    expect(screen.getByText("standard")).toBeTruthy();
    expect(screen.getByText("raptor")).toBeTruthy();
    expect(screen.getByText("Rerank")).toBeTruthy();
    expect(screen.getByText("Continue conversation")).toBeTruthy();
  });
});

function queryResponse(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    answer: "The refund policy allows 30 days.",
    sources: [],
    confidence: 0.9,
    model_used: "llama3",
    method: "standard",
    ...overrides,
  };
}

describe("QueryResultCard", () => {
  it("shows confidence, model, and method", () => {
    render(<QueryResultCard response={queryResponse()} />);
    expect(screen.getByText("90% confidence")).toBeTruthy();
    expect(screen.getByText(/Model: llama3/)).toBeTruthy();
    expect(screen.getByText(/Method: standard/)).toBeTruthy();
  });

  it("copies the answer text to the clipboard and shows a checkmark", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(<QueryResultCard response={queryResponse()} />);

    fireEvent.click(screen.getByLabelText("Copy answer"));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("The refund policy allows 30 days."),
    );
    await screen.findByText("✓");
    vi.unstubAllGlobals();
  });

  it("shows a token count when present", () => {
    render(<QueryResultCard response={queryResponse({ tokens_used: 42 })} />);
    expect(screen.getByText(/\(42 tokens\)/)).toBeTruthy();
  });

  it("shows a degraded warning when method_details.degraded is non-empty", () => {
    render(
      <QueryResultCard
        response={queryResponse({
          method_details: { retrieval: "dense", degraded: ["rerank"] },
        })}
      />,
    );
    expect(screen.getByText(/Degraded: rerank/)).toBeTruthy();
  });

  it("shows the metadata filter source when present", () => {
    render(
      <QueryResultCard
        response={queryResponse({
          method_details: { retrieval: "dense", metadata_filter: { source: "handbook.pdf" } },
        })}
      />,
    );
    expect(screen.getByText(/Filtered to: handbook.pdf/)).toBeTruthy();
  });

  it("shows sources unless compact", () => {
    const response = queryResponse({
      sources: [{ text: "Refunds are allowed within 30 days of purchase.", source: "handbook.pdf", score: 0.87 }],
    });
    const { rerender } = render(<QueryResultCard response={response} />);
    expect(screen.getByText("Sources")).toBeTruthy();

    rerender(<QueryResultCard response={response} compact />);
    expect(screen.queryByText("Sources")).toBeNull();
  });

  it("truncates a long source snippet with an ellipsis", () => {
    const longText = "x".repeat(250);
    render(
      <QueryResultCard
        response={queryResponse({ sources: [{ text: longText, source: "a.pdf", score: 0.5 }] })}
      />,
    );
    expect(screen.getByText((t) => t.endsWith("…"))).toBeTruthy();
  });
});

const kb: KnowledgeBase = { id: "kb-1", name: "Support docs" };

describe("CreatePipelineForm", () => {
  it("prompts to create a knowledge base first when none exist", () => {
    render(<CreatePipelineForm token="tok" kbs={[]} onCreated={vi.fn()} />);
    expect(screen.getByText(/Create a knowledge base first/)).toBeTruthy();
  });

  it("requires a name", async () => {
    render(<CreatePipelineForm token="tok" kbs={[kb]} onCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await screen.findByText("Name is required.");
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("requires at least one knowledge base", async () => {
    render(<CreatePipelineForm token="tok" kbs={[kb]} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My pipeline" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    await screen.findByText("Pick at least one knowledge base.");
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("creates a pipeline and resets the form", async () => {
    apiFetch.mockResolvedValue({
      pipeline_id: "p-1",
      name: "My pipeline",
      knowledge_base_ids: ["kb-1"],
      created_at: "2026-01-01T00:00:00Z",
    });
    const onCreated = vi.fn();
    render(<CreatePipelineForm token="tok" kbs={[kb]} onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My pipeline" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(onCreated).toHaveBeenCalledWith({
        id: "p-1",
        name: "My pipeline",
        knowledge_base_ids: ["kb-1"],
        created_at: "2026-01-01T00:00:00Z",
      }),
    );
    expect(apiFetch).toHaveBeenCalledWith("/v1/rag/pipeline", {
      method: "POST",
      body: { name: "My pipeline", knowledge_base_ids: ["kb-1"] },
      token: "tok",
    });
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("");
  });

  it("shows a friendly error on failure and leaves creating re-enabled", async () => {
    apiFetch.mockRejectedValue(new Error("rag-pipeline unreachable"));
    render(<CreatePipelineForm token="tok" kbs={[kb]} onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "My pipeline" } });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await screen.findByText("rag-pipeline unreachable");
    expect(
      (screen.getByRole("button", { name: "Create" }) as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  it("shows a login hint and disables submit when logged out", () => {
    render(<CreatePipelineForm token="" kbs={[kb]} onCreated={vi.fn()} />);
    expect(screen.getByText("Log in to create a pipeline.")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Create" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

const caps: Capabilities = {
  methods: {
    standard: true,
    conversational: true,
    hyde: true,
    self_rag: true,
    auto: true,
    corrective: true,
    raptor: true,
  },
  enhancers: {
    rerank: { available: true, backend: "cross-encoder" },
    compress: { available: true },
  },
  retrievers: {
    dense: { available: true },
    hybrid: { available: true },
    parent_child: { available: true },
    metadata_filter: { available: true },
  },
};

describe("QueryPanel", () => {
  it("disables the form and shows a login hint when logged out", () => {
    render(<QueryPanel pipelineId="p-1" token="" capabilities={caps} onGone={vi.fn()} />);
    expect(screen.getByText("Log in to query.")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "Ask" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("requires a question", async () => {
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Question is required.");
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("submits the default top_k and method", async () => {
    apiFetch.mockResolvedValue(queryResponse());
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Question"), {
      target: { value: "What is the refund policy?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText("The refund policy allows 30 days.");
    expect(apiFetch).toHaveBeenCalledWith("/v1/rag/pipeline/p-1/query", {
      method: "POST",
      body: {
        question: "What is the refund policy?",
        top_k: 5,
        method: "standard",
        rerank: false,
        compress: false,
        hybrid: false,
        parent_context: false,
      },
      token: "tok",
    });
  });

  it("falls back to top_k=5 for an emptied top_k field instead of sending NaN", async () => {
    // Not a negative value: the input's own `min={1}` blocks form submission
    // entirely on an out-of-range value (jsdom implements HTML5 constraint
    // validation), so the only way this NaN-guard branch is actually
    // reachable through real user interaction is an emptied (not `required`)
    // field, which parseInt("", 10) turns into NaN.
    apiFetch.mockResolvedValue(queryResponse());
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    fireEvent.change(screen.getByLabelText("Top K"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const body = apiFetch.mock.calls[0][1].body;
    expect(body.top_k).toBe(5);
  });

  it("forces hybrid off while parent context retrieval is on", async () => {
    apiFetch.mockResolvedValue(queryResponse());
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.click(screen.getByText("Advanced retrieval options"));
    fireEvent.click(screen.getByLabelText(/Hybrid retrieval/));
    fireEvent.click(screen.getByLabelText("Parent context retrieval"));
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const body = apiFetch.mock.calls[0][1].body;
    expect(body.hybrid).toBe(false);
    expect(body.parent_context).toBe(true);
  });

  it("sends a metadata_filter when a source filename is set", async () => {
    apiFetch.mockResolvedValue(queryResponse());
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.click(screen.getByText("Advanced retrieval options"));
    fireEvent.change(screen.getByLabelText("Filter by filename"), {
      target: { value: "handbook.pdf" },
    });
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    expect(apiFetch.mock.calls[0][1].body.metadata_filter).toEqual({ source: "handbook.pdf" });
  });

  it("accumulates turns and reuses one conversation_id in continue-conversation mode", async () => {
    apiFetch.mockResolvedValue(queryResponse({ answer: "first answer" }));
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.click(screen.getByText("Advanced retrieval options"));
    fireEvent.click(screen.getByLabelText(/Continue conversation/));
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "turn one" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Q: turn one");

    const firstConvId = apiFetch.mock.calls[0][1].body.conversation_id;
    expect(firstConvId).toBeTruthy();

    apiFetch.mockResolvedValue(queryResponse({ answer: "second answer" }));
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "turn two" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Q: turn two");

    expect(screen.getByText("Conversation (2 turns)")).toBeTruthy();
    expect(apiFetch.mock.calls[1][1].body.conversation_id).toBe(firstConvId);
    // The question box clears between turns, chat-style.
    expect((screen.getByLabelText("Question") as HTMLTextAreaElement).value).toBe("");
  });

  it("resets the conversation thread on demand", async () => {
    apiFetch.mockResolvedValue(queryResponse());
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.click(screen.getByText("Advanced retrieval options"));
    fireEvent.click(screen.getByLabelText(/Continue conversation/));
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "hi" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Conversation (1 turn)");

    fireEvent.click(screen.getByText("Reset conversation"));
    expect(screen.queryByText(/Conversation \(/)).toBeNull();
  });

  it("shows a removed-pipeline message and calls onGone on a 404", async () => {
    apiFetch.mockRejectedValue(new ApiError("not found", 404));
    const onGone = vi.fn();
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={onGone} />);

    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText(/no longer exists on the server/);
    expect(onGone).toHaveBeenCalled();
  });

  it("shows a friendly error on a non-404 failure", async () => {
    apiFetch.mockRejectedValue(new Error("rag-pipeline unreachable"));
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={caps} onGone={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "q" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText("rag-pipeline unreachable");
  });

  it("marks a method unavailable on this host and disables its option", () => {
    render(
      <QueryPanel
        pipelineId="p-1"
        token="tok"
        capabilities={{ ...caps, methods: { ...caps.methods, hyde: false } }}
        onGone={vi.fn()}
      />,
    );
    const option = screen.getByRole("option", { name: /hyde/ }) as HTMLOptionElement;
    expect(option.disabled).toBe(true);
    expect(option.textContent).toContain("unavailable on this host");
  });

  it("treats an absent method flag as available (no disabled flicker before capabilities load)", () => {
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={null} onGone={vi.fn()} />);
    const option = screen.getByRole("option", { name: "raptor" }) as HTMLOptionElement;
    expect(option.disabled).toBe(false);
  });

  it("defaults enhancer checkboxes to disabled while capabilities is absent", () => {
    render(<QueryPanel pipelineId="p-1" token="tok" capabilities={null} onGone={vi.fn()} />);
    fireEvent.click(screen.getByText("Advanced retrieval options"));
    expect((screen.getByLabelText(/^Rerank/) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText(/^Compress/) as HTMLInputElement).disabled).toBe(true);
  });
});

function pipeline(overrides: Partial<RagPipeline> = {}): RagPipeline {
  return {
    id: "p-1",
    name: "Support pipeline",
    knowledge_base_ids: ["kb-1"],
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("PipelineCard", () => {
  it("shows a login hint and disables rename/delete when logged out", () => {
    render(
      <PipelineCard
        pipeline={pipeline()}
        token=""
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={vi.fn()}
        confirm={vi.fn()}
      />,
    );
    expect(screen.getByText("Log in to rename or delete this pipeline.")).toBeTruthy();
    expect(
      (screen.getByRole("button", { name: "✏️ Rename" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      (screen.getByRole("button", { name: "🗑 Delete" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("rejects an empty name on rename", async () => {
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={vi.fn()}
        confirm={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Rename" }));
    fireEvent.change(screen.getByLabelText("Pipeline name"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Name can't be empty.");
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("saves a rename and exits edit mode", async () => {
    apiFetch.mockResolvedValue(pipeline({ name: "Renamed" }));
    const onUpdated = vi.fn();
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={onUpdated}
        confirm={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Rename" }));
    fireEvent.change(screen.getByLabelText("Pipeline name"), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onUpdated).toHaveBeenCalledWith(pipeline({ name: "Renamed" })));
    expect(apiFetch).toHaveBeenCalledWith("/v1/rag/pipeline/p-1", {
      method: "PATCH",
      body: { name: "Renamed" },
      token: "tok",
    });
    expect(screen.queryByLabelText("Pipeline name")).toBeNull();
  });

  it("cancels a rename without saving", () => {
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={vi.fn()}
        confirm={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Rename" }));
    fireEvent.change(screen.getByLabelText("Pipeline name"), { target: { value: "Discard me" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Support pipeline")).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("does not delete when the confirmation is declined", async () => {
    const confirm = vi.fn().mockResolvedValue(false);
    const onDeleted = vi.fn();
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={onDeleted}
        onUpdated={vi.fn()}
        confirm={confirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());

    expect(apiFetch).not.toHaveBeenCalled();
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes once confirmed", async () => {
    apiFetch.mockResolvedValue({});
    const confirm = vi.fn().mockResolvedValue(true);
    const onDeleted = vi.fn();
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={onDeleted}
        onUpdated={vi.fn()}
        confirm={confirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p-1"));
    expect(apiFetch).toHaveBeenCalledWith("/v1/rag/pipeline/p-1", {
      method: "DELETE",
      token: "tok",
    });
  });

  it("treats a 404 on delete as already-gone, not an error", async () => {
    apiFetch.mockRejectedValue(new ApiError("not found", 404));
    const confirm = vi.fn().mockResolvedValue(true);
    const onDeleted = vi.fn();
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={onDeleted}
        onUpdated={vi.fn()}
        confirm={confirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p-1"));
  });

  it("shows a friendly error on a non-404 delete failure", async () => {
    apiFetch.mockRejectedValue(new Error("rag-pipeline unreachable"));
    const confirm = vi.fn().mockResolvedValue(true);
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={vi.fn()}
        confirm={confirm}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await screen.findByText("rag-pipeline unreachable");
  });

  it("does not crash when the copy-id button is clicked", () => {
    render(
      <PipelineCard
        pipeline={pipeline()}
        token="tok"
        capabilities={null}
        onDeleted={vi.fn()}
        onUpdated={vi.fn()}
        confirm={vi.fn()}
      />,
    );
    expect(() => fireEvent.click(screen.getByText("Copy"))).not.toThrow();
  });
});

describe("RagPipelinesPage", () => {
  it("loads knowledge bases, capabilities, and pipelines on mount", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases")) return Promise.resolve({ items: [kb] });
      if (path === "/v1/rag/capabilities") return Promise.resolve(caps);
      if (path.startsWith("/v1/rag/pipeline?")) return Promise.resolve({ items: [pipeline()] });
      if (path === "/v1/rag/decision-stats") return Promise.resolve(null);
      throw new Error(`unexpected path ${path}`);
    });
    render(<RagPipelinesPage />);

    expect(await screen.findByText("Support pipeline")).toBeTruthy();
  });

  it("degrades gracefully when decision-stats 404s (older backend)", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases")) return Promise.resolve({ items: [] });
      if (path === "/v1/rag/capabilities") return Promise.resolve(caps);
      if (path.startsWith("/v1/rag/pipeline?")) return Promise.resolve({ items: [] });
      if (path === "/v1/rag/decision-stats") return Promise.reject(new ApiError("not found", 404));
      throw new Error(`unexpected path ${path}`);
    });
    render(<RagPipelinesPage />);

    await screen.findByText(/No pipelines created yet/);
    // The whole page loaded fine despite decision-stats failing.
    expect(screen.queryByText(/Auto-router analytics/)).toBeNull();
  });

  it("shows a friendly error status when the initial load fails", async () => {
    apiFetch.mockRejectedValue(new Error("rag-pipeline unreachable"));
    render(<RagPipelinesPage />);

    await screen.findByText("rag-pipeline unreachable");
  });

  it("filters pipelines by name", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases")) return Promise.resolve({ items: [] });
      if (path === "/v1/rag/capabilities") return Promise.resolve(caps);
      if (path.startsWith("/v1/rag/pipeline?")) {
        return Promise.resolve({
          items: [pipeline({ id: "p-1", name: "Support" }), pipeline({ id: "p-2", name: "Sales" })],
        });
      }
      if (path === "/v1/rag/decision-stats") return Promise.resolve(null);
      throw new Error(`unexpected path ${path}`);
    });
    render(<RagPipelinesPage />);
    await screen.findByText("Support");

    fireEvent.change(screen.getByLabelText("Filter pipelines"), { target: { value: "sal" } });

    expect(screen.getByText("Sales")).toBeTruthy();
    expect(screen.queryByText("Support")).toBeNull();
    expect(screen.getByText("1 of 2")).toBeTruthy();
  });

  it("shows a no-match empty state when the filter matches nothing", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases")) return Promise.resolve({ items: [] });
      if (path === "/v1/rag/capabilities") return Promise.resolve(caps);
      if (path.startsWith("/v1/rag/pipeline?")) {
        return Promise.resolve({
          items: [pipeline({ id: "p-1", name: "Support" }), pipeline({ id: "p-2", name: "Sales" })],
        });
      }
      if (path === "/v1/rag/decision-stats") return Promise.resolve(null);
      throw new Error(`unexpected path ${path}`);
    });
    render(<RagPipelinesPage />);
    await screen.findByText("Support");

    fireEvent.change(screen.getByLabelText("Filter pipelines"), { target: { value: "nope" } });

    await screen.findByText('No pipelines match "nope".');
  });
});
