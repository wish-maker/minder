import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GraphExplorerPage } from "./GraphExplorerPage";

let statsResult: Record<string, unknown> = {
  success: true,
  nodes: 0,
  relationships: 0,
  documents: 0,
  entities: 0,
  entity_types: {},
};
let documentsResult: Record<string, unknown> = { success: true, documents: [], count: 0 };
let extractBehavior: () => Promise<unknown>;
let buildBehavior: () => Promise<unknown>;
let deleteBehavior: () => Promise<unknown>;
let statsBehavior: (() => Promise<unknown>) | null = null;
let lastDeletePath: string | undefined;
const confirmMock = vi.fn();

// The three retrieval modes (Search/Find entities/Entity lookup, #701) each
// hit a different endpoint -- each has its own overridable behavior so a
// test can inject a rejection without disturbing the other two, and its own
// captured request options to assert the right query/body was sent.
let searchBehavior: () => Promise<unknown>;
let retrieveBehavior: () => Promise<unknown>;
let entityBehavior: () => Promise<unknown>;
let lastSearchOpts: { body?: { query?: string } } | undefined;
let lastRetrieveOpts: { body?: { query?: string } } | undefined;
let lastEntityOpts: { body?: { entity_text?: string } } | undefined;

function resetBehaviors() {
  searchBehavior = async () => ({
    success: true,
    query: "tesla",
    entities: [
      { text: "Tesla", label: "ORG" },
      { text: "Tesla Model 3", label: "PRODUCT" },
    ],
    entity_count: 2,
  });
  retrieveBehavior = async () => ({
    success: true,
    query: "who runs tesla",
    related_entities: [{ text: "Elon Musk" }],
    entity_count: 1,
    retrieval_time_ms: 12,
  });
  entityBehavior = async () => ({
    success: true,
    entity: { text: "Elon Musk", label: "PERSON" },
    related_entities: [{ text: "Tesla" }],
    documents: [{ id: "d1", title: "bio.txt" }],
    context_window: 5,
  });
  extractBehavior = async () => ({
    success: true,
    entities: [{ text: "Tesla", label: "ORG" }],
    relationships: [{ source: "Tesla", type: "FOUNDED_BY", target: "Elon Musk" }],
    entity_count: 1,
    relationship_count: 1,
  });
  buildBehavior = async () => ({
    success: true,
    message: "Graph built",
    document_id: "doc-1",
    entity_count: 3,
    relationship_count: 2,
  });
  deleteBehavior = async () => ({ success: true });
}
resetBehaviors();

const apiFetch = vi.fn(async (path: string, opts?: unknown) => {
  if (path.includes("/graph/stats")) return statsBehavior ? statsBehavior() : statsResult;
  if (path.includes("/graph/documents")) return documentsResult;
  if (path.includes("/graph/search")) {
    lastSearchOpts = opts as typeof lastSearchOpts;
    return searchBehavior();
  }
  if (path.includes("/retrieve")) {
    lastRetrieveOpts = opts as typeof lastRetrieveOpts;
    return retrieveBehavior();
  }
  if (path.includes("/entity-context")) {
    lastEntityOpts = opts as typeof lastEntityOpts;
    return entityBehavior();
  }
  if (path.includes("/extract")) return extractBehavior();
  if (path.includes("/construct-graph")) return buildBehavior();
  if (path.includes("/graph/document/")) {
    lastDeletePath = path;
    return deleteBehavior();
  }
  return {};
});

vi.mock("../lib/api", () => ({
  apiFetch: (path: string, opts?: unknown) => apiFetch(path, opts),
  friendlyErrorMessage: (e: unknown) => String(e),
}));
vi.mock("../lib/auth", () => ({
  useAuth: () => ({ token: "test-token" }),
}));
vi.mock("../components/ConfirmDialog", () => ({
  useConfirm: () => ({ confirm: confirmMock, dialog: null }),
}));

afterEach(() => {
  cleanup();
  apiFetch.mockClear();
  confirmMock.mockReset();
  statsBehavior = null;
  lastSearchOpts = lastRetrieveOpts = lastEntityOpts = lastDeletePath = undefined;
  statsResult = {
    success: true,
    nodes: 0,
    relationships: 0,
    documents: 0,
    entities: 0,
    entity_types: {},
  };
  documentsResult = { success: true, documents: [], count: 0 };
  resetBehaviors();
});

describe("GraphExplorerPage — Find entities (graph search)", () => {
  it("searches the graph for entities and renders the matches", async () => {
    render(<GraphExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Find entities" }));
    fireEvent.change(
      screen.getByLabelText("Find entities by name or label"),
      { target: { value: "tesla" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Find" }));

    expect(await screen.findByText("Tesla")).toBeTruthy();
    expect(screen.getByText("Tesla Model 3")).toBeTruthy();
    await waitFor(() => expect(lastSearchOpts?.body?.query).toBe("tesla"));
  });

  it("shows an empty-state message when nothing matches", async () => {
    searchBehavior = async () => ({
      success: true,
      query: "zzz",
      entities: [],
      entity_count: 0,
    });
    render(<GraphExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Find entities" }));
    fireEvent.change(
      screen.getByLabelText("Find entities by name or label"),
      { target: { value: "zzz" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Find" }));

    expect(await screen.findByText(/No entities match/i)).toBeTruthy();
  });

  it("shows a friendly error when the search request fails", async () => {
    searchBehavior = async () => {
      throw new Error("graph-rag unreachable");
    };
    render(<GraphExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Find entities" }));
    fireEvent.change(
      screen.getByLabelText("Find entities by name or label"),
      { target: { value: "tesla" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Find" }));

    expect(await screen.findByText("Error: graph-rag unreachable")).toBeTruthy();
  });
});

describe("GraphExplorerPage — Search (graph-based retrieval)", () => {
  it("retrieves related entities for a query (default tab)", async () => {
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Search the knowledge graph"), {
      target: { value: "who runs tesla" },
    });
    // Two "Search" buttons exist simultaneously (the tab + the submit button,
    // since "search" is the default mode) -- the submit button is the last one.
    fireEvent.click(screen.getAllByRole("button", { name: "Search" }).at(-1)!);

    expect(await screen.findByText("Elon Musk")).toBeTruthy();
    await waitFor(() =>
      expect(lastRetrieveOpts?.body?.query).toBe("who runs tesla"),
    );
  });

  it("requires non-empty query text before calling the API", () => {
    render(<GraphExplorerPage />);
    fireEvent.click(screen.getAllByRole("button", { name: "Search" }).at(-1)!);

    expect(screen.getByText("Query is required.")).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalledWith(
      "/v1/graph-rag/retrieve",
      expect.anything(),
    );
  });

  it("shows a friendly error when the retrieve request fails", async () => {
    retrieveBehavior = async () => {
      throw new Error("neo4j unreachable");
    };
    render(<GraphExplorerPage />);
    fireEvent.change(screen.getByLabelText("Search the knowledge graph"), {
      target: { value: "who runs tesla" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Search" }).at(-1)!);

    expect(await screen.findByText("Error: neo4j unreachable")).toBeTruthy();
  });
});

describe("GraphExplorerPage — Entity lookup", () => {
  it("looks up an entity and renders its neighbors and documents", async () => {
    render(<GraphExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Entity lookup" }));
    fireEvent.change(screen.getByLabelText("Entity name to look up"), {
      target: { value: "Elon Musk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));

    await screen.findByText("Elon Musk"); // the looked-up entity's own name
    expect(screen.getByText("Tesla")).toBeTruthy(); // related entity
    expect(screen.getByText(/Mentioned in: bio.txt/)).toBeTruthy();
    await waitFor(() =>
      expect(lastEntityOpts?.body?.entity_text).toBe("Elon Musk"),
    );
  });

  it("shows 'Entity not found' for an empty entity result", async () => {
    entityBehavior = async () => ({
      success: true,
      entity: {},
      related_entities: [],
      documents: [],
      context_window: 5,
    });
    render(<GraphExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Entity lookup" }));
    fireEvent.change(screen.getByLabelText("Entity name to look up"), {
      target: { value: "Nobody" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));

    expect(
      await screen.findByText("Entity not found in the graph."),
    ).toBeTruthy();
  });

  it("shows a friendly error when the entity-context request fails", async () => {
    entityBehavior = async () => {
      throw new Error("entity lookup failed");
    };
    render(<GraphExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "Entity lookup" }));
    fireEvent.change(screen.getByLabelText("Entity name to look up"), {
      target: { value: "Elon Musk" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));

    expect(await screen.findByText("Error: entity lookup failed")).toBeTruthy();
  });
});

describe("GraphExplorerPage — Graph overview", () => {
  it("shows the empty-graph message when there are zero nodes", async () => {
    render(<GraphExplorerPage />);
    expect(
      await screen.findByText(/The graph is empty — build a document/),
    ).toBeTruthy();
  });

  it("renders stat tiles and entity-type badges when the graph is non-empty", async () => {
    statsResult = {
      success: true,
      nodes: 12,
      relationships: 5,
      documents: 3,
      entities: 8,
      entity_types: { PERSON: 4, ORG: 2 },
    };
    render(<GraphExplorerPage />);

    expect(await screen.findByText("entities")).toBeTruthy();
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText("relationships")).toBeTruthy();
    expect(screen.getByText("PERSON")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText("ORG")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
  });

  it("reloads stats when Refresh is clicked", async () => {
    render(<GraphExplorerPage />);
    await screen.findByText(/The graph is empty/);
    apiFetch.mockClear();

    fireEvent.click(screen.getAllByRole("button", { name: "Refresh" })[0]);

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/graph-rag/graph/stats",
        expect.objectContaining({}),
      ),
    );
  });

  it("shows a friendly error when the stats fetch fails", async () => {
    statsBehavior = async () => {
      throw new Error("graph-rag unreachable");
    };
    render(<GraphExplorerPage />);

    expect(await screen.findByText("Error: graph-rag unreachable")).toBeTruthy();
  });
});

describe("GraphExplorerPage — Extract & Build", () => {
  it("requires text before previewing or building", async () => {
    render(<GraphExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Preview extraction" }));
    expect(await screen.findByText("Text is required.")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Build knowledge graph" }));
    expect(await screen.findByText("Text is required.")).toBeTruthy();
  });

  it("previews extracted entities and relationships without building anything", async () => {
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Text"), {
      target: { value: "Tesla was founded by Elon Musk." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Preview extraction" }));

    expect(
      await screen.findByText("1 entities, 1 relationships found — nothing saved yet."),
    ).toBeTruthy();
    expect(screen.getByText(/Tesla —\[FOUNDED_BY\]→ Elon Musk/)).toBeTruthy();
    expect(apiFetch).not.toHaveBeenCalledWith(
      "/v1/graph-rag/construct-graph",
      expect.anything(),
    );
  });

  it("shows a friendly error when preview extraction fails", async () => {
    extractBehavior = async () => {
      throw new Error("spaCy model not loaded");
    };
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Text"), { target: { value: "some text" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview extraction" }));

    expect(await screen.findByText("Error: spaCy model not loaded")).toBeTruthy();
  });

  it("builds the graph, reports the result, and refreshes the overview/document list", async () => {
    render(<GraphExplorerPage />);
    apiFetch.mockClear();

    fireEvent.change(screen.getByLabelText("Text"), {
      target: { value: "Tesla was founded by Elon Musk." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Build knowledge graph" }));

    expect(await screen.findByText(/Graph built/)).toBeTruthy();
    expect(screen.getByText("doc-1")).toBeTruthy();
    // handleChanged() re-fetches both stats and the document list after a build.
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/graph-rag/graph/stats",
        expect.objectContaining({}),
      ),
    );
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        "/v1/graph-rag/graph/documents",
        expect.objectContaining({}),
      ),
    );
  });

  it("shows a friendly error when build fails", async () => {
    buildBehavior = async () => {
      throw new Error("neo4j unreachable");
    };
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Text"), { target: { value: "some text" } });
    fireEvent.click(screen.getByRole("button", { name: "Build knowledge graph" }));

    expect(await screen.findByText("Error: neo4j unreachable")).toBeTruthy();
  });
});

describe("GraphExplorerPage — Remove a document's graph", () => {
  it("lists documents in the graph and selects one into the id field on click", async () => {
    documentsResult = {
      success: true,
      documents: [
        { id: "doc-1", title: "Board notes", source: null, created_at: null, entity_count: 4 },
      ],
      count: 1,
    };
    render(<GraphExplorerPage />);

    const docButton = await screen.findByText(/Board notes — 4 entities/);
    fireEvent.click(docButton);

    expect((screen.getByLabelText("Document id") as HTMLInputElement).value).toBe("doc-1");
  });

  it("shows a fallback title/source when both are null", async () => {
    documentsResult = {
      success: true,
      documents: [
        { id: "", title: null, source: null, created_at: null, entity_count: 0 },
      ],
      count: 1,
    };
    render(<GraphExplorerPage />);

    expect(await screen.findByText(/Untitled — 0 entities/)).toBeTruthy();
    expect(screen.getByText("(—)")).toBeTruthy();
  });

  it("requires a document id before deleting", async () => {
    render(<GraphExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Document id is required.")).toBeTruthy();
    expect(confirmMock).not.toHaveBeenCalled();
  });

  it("does not delete when the confirmation is declined", async () => {
    confirmMock.mockResolvedValue(false);
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Document id"), {
      target: { value: "doc-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(confirmMock).toHaveBeenCalled());
    expect(apiFetch).not.toHaveBeenCalledWith(
      expect.stringContaining("/graph/document/"),
      expect.anything(),
    );
  });

  it("deletes the document once confirmed, reports success, and clears the field", async () => {
    confirmMock.mockResolvedValue(true);
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Document id"), {
      target: { value: "doc-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(
      await screen.findByText(/Deleted \(idempotent/),
    ).toBeTruthy();
    expect(lastDeletePath).toBe("/v1/graph-rag/graph/document/doc-1");
    expect((screen.getByLabelText("Document id") as HTMLInputElement).value).toBe("");
  });

  it("shows a friendly error when delete fails", async () => {
    confirmMock.mockResolvedValue(true);
    deleteBehavior = async () => {
      throw new Error("neo4j unreachable");
    };
    render(<GraphExplorerPage />);

    fireEvent.change(screen.getByLabelText("Document id"), {
      target: { value: "doc-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(await screen.findByText("Error: neo4j unreachable")).toBeTruthy();
  });
});
