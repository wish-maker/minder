import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChunkViewer } from "./KnowledgeBasesPage";

const apiFetch = vi.fn();

vi.mock("../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  friendlyErrorMessage: (e: unknown) => (e instanceof Error ? e.message : "error"),
}));

// ChunkViewer is a pure presentational component (lazy-loads a document's
// stored chunk text on first expand) -- test it directly by prop, no full
// page mount needed, matching AutoRouterStatsCard's precedent.
describe("ChunkViewer", () => {
  afterEach(() => {
    apiFetch.mockReset();
    cleanup();
  });

  it("fetches chunks only once expanded, not on initial render", () => {
    render(<ChunkViewer kbId="kb-1" documentId="doc-1" />);
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("fetches and renders chunks in order when expanded", async () => {
    apiFetch.mockResolvedValue({
      items: [
        { chunk_index: 0, text: "Acme makes widgets." },
        { chunk_index: 1, text: "Founded in 1999." },
      ],
      total: 2,
      limit: 500,
      offset: 0,
    });
    render(<ChunkViewer kbId="kb-1" documentId="doc-1" />);

    fireEvent.click(screen.getByText("View chunks"));

    await screen.findByText("Acme makes widgets.");
    expect(screen.getByText("Founded in 1999.")).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/rag/knowledge-bases/kb-1/documents/doc-1/chunks?limit=500",
    );
  });

  it("does not re-fetch on a second expand", async () => {
    apiFetch.mockResolvedValue({
      items: [{ chunk_index: 0, text: "hello" }],
      total: 1,
      limit: 500,
      offset: 0,
    });
    const { container } = render(<ChunkViewer kbId="kb-1" documentId="doc-1" />);
    const summary = screen.getByText("View chunks");
    const details = container.querySelector("details")!;

    // jsdom's native <details> "toggle" event (what onToggle listens for)
    // resolves asynchronously relative to the click -- each click must be
    // awaited to settle before the next, or a rapid click/click pair can
    // net out to no observed state change at all (confirmed live: without
    // these awaits, this test passed even with the loaded-guard removed).
    fireEvent.click(summary); // open
    await waitFor(() => expect(details.open).toBe(true));
    await screen.findByText("hello");

    fireEvent.click(summary); // close
    await waitFor(() => expect(details.open).toBe(false));

    fireEvent.click(summary); // re-open
    await waitFor(() => expect(details.open).toBe(true));

    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("shows a friendly error when the fetch fails", async () => {
    apiFetch.mockRejectedValue(new Error("Knowledge base not found"));
    render(<ChunkViewer kbId="kb-1" documentId="doc-1" />);

    fireEvent.click(screen.getByText("View chunks"));

    await screen.findByText("Knowledge base not found");
  });
});
