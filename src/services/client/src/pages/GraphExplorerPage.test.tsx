import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GraphExplorerPage } from "./GraphExplorerPage";

// apiFetch is dispatched by request path: stats/documents fire on mount (via
// useAsyncResource), and /graph/search is the new "Find entities" endpoint (#701).
let lastSearchOpts: { body?: { query?: string } } | undefined;

const apiFetch = vi.fn(async (path: string, opts?: unknown) => {
  if (path.includes("/graph/search")) {
    lastSearchOpts = opts as { body?: { query?: string } };
  }
  if (path.includes("/graph/stats")) {
    return {
      success: true,
      nodes: 0,
      relationships: 0,
      documents: 0,
      entities: 0,
      entity_types: {},
    };
  }
  if (path.includes("/graph/documents")) {
    return { success: true, documents: [], count: 0 };
  }
  if (path.includes("/graph/search")) {
    return {
      success: true,
      query: "tesla",
      entities: [
        { text: "Tesla", label: "ORG" },
        { text: "Tesla Model 3", label: "PRODUCT" },
      ],
      entity_count: 2,
    };
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
  useConfirm: () => ({ confirm: vi.fn(), dialog: null }),
}));

describe("GraphExplorerPage — Find entities (graph search)", () => {
  afterEach(() => {
    cleanup();
    apiFetch.mockClear();
    lastSearchOpts = undefined;
  });

  it("searches the graph for entities and renders the matches", async () => {
    render(<GraphExplorerPage />);

    // Switch to the new "Find entities" tab and run a query.
    fireEvent.click(screen.getByRole("button", { name: "Find entities" }));
    fireEvent.change(
      screen.getByLabelText("Find entities by name or label"),
      { target: { value: "tesla" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Find" }));

    // Both matching entities render.
    expect(await screen.findByText("Tesla")).toBeTruthy();
    expect(screen.getByText("Tesla Model 3")).toBeTruthy();

    // The new /v1/graph/search endpoint was hit with the typed query.
    await waitFor(() => {
      expect(lastSearchOpts?.body?.query).toBe("tesla");
    });
  });

  it("shows an empty-state message when nothing matches", async () => {
    apiFetch.mockImplementationOnce(async () => ({
      success: true,
      nodes: 0,
      relationships: 0,
      documents: 0,
      entities: 0,
      entity_types: {},
    }));
    apiFetch.mockImplementation(async (path: string) => {
      if (path.includes("/graph/search")) {
        return { success: true, query: "zzz", entities: [], entity_count: 0 };
      }
      if (path.includes("/graph/documents")) {
        return { success: true, documents: [], count: 0 };
      }
      return {
        success: true,
        nodes: 0,
        relationships: 0,
        documents: 0,
        entities: 0,
        entity_types: {},
      };
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
});
