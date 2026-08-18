import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ChunkViewer,
  CreateKbForm,
  DocumentsList,
  KnowledgeBaseCard,
  KnowledgeBasesPage,
  UploadWidget,
  type KnowledgeBase,
} from "./KnowledgeBasesPage";

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

function kb(overrides: Partial<KnowledgeBase> = {}): KnowledgeBase {
  return {
    id: "kb-1",
    name: "Support docs",
    description: "Customer-facing help articles",
    embedding_model: "nomic-embed-text",
    llm_model: "llama3",
    document_count: 2,
    vector_count: 40,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

// jsdom's File doesn't implement enough for the component's needs; the
// component only ever reads `.name` off each queued file and hands the File
// straight to FormData, so a plain object satisfying just that is enough.
function fakeFile(name: string) {
  return { name };
}

afterEach(() => {
  apiFetch.mockReset();
  cleanup();
});

// ChunkViewer is a pure presentational component (lazy-loads a document's
// stored chunk text on first expand) -- test it directly by prop, no full
// page mount needed.
describe("ChunkViewer", () => {
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

describe("UploadWidget", () => {
  it("shows a login hint and disables the file input when logged out", () => {
    render(<UploadWidget kb={kb()} token="" onUploaded={vi.fn()} />);
    expect(screen.getByText("Log in to upload documents.")).toBeTruthy();
    expect(
      (screen.getByLabelText(/Upload documents/) as HTMLInputElement).disabled,
    ).toBe(true);
  });

  it("queues selected files and does not show the upload button until files are chosen", () => {
    render(<UploadWidget kb={kb()} token="tok" onUploaded={vi.fn()} />);
    expect(screen.queryByText("Upload all")).toBeNull();

    fireEvent.change(screen.getByLabelText(/Upload documents/), {
      target: { files: [fakeFile("handbook.pdf")] },
    });

    expect(screen.getByText(/handbook.pdf — queued/)).toBeTruthy();
    expect(screen.getByText("Upload all")).toBeTruthy();
  });

  it("uploads each queued file and reports per-file results", async () => {
    apiFetch.mockResolvedValue({
      message: "ok",
      chunks_processed: 3,
      vectors_created: 3,
      filename: "handbook.pdf",
      document_id: "doc-1",
    });
    const onUploaded = vi.fn();
    render(<UploadWidget kb={kb()} token="tok" onUploaded={onUploaded} />);

    fireEvent.change(screen.getByLabelText(/Upload documents/), {
      target: { files: [fakeFile("handbook.pdf")] },
    });
    fireEvent.click(screen.getByText("Upload all"));

    await screen.findByText(/handbook.pdf — done: 3 chunks, 3 vectors/);
    expect(onUploaded).toHaveBeenCalled();
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/rag/knowledge-bases/kb-1/upload",
      expect.objectContaining({ method: "POST", token: "tok" }),
    );
  });

  it("includes build_tree in the form data when the checkbox is on", async () => {
    apiFetch.mockResolvedValue({
      message: "ok",
      chunks_processed: 1,
      vectors_created: 1,
      filename: "a.pdf",
      document_id: "doc-1",
      tree_nodes_created: 4,
    });
    render(<UploadWidget kb={kb()} token="tok" onUploaded={vi.fn()} />);

    fireEvent.click(screen.getByLabelText(/Build search tree/));
    fireEvent.change(screen.getByLabelText(/Upload documents/), {
      target: { files: [fakeFile("a.pdf")] },
    });
    fireEvent.click(screen.getByText("Upload all"));

    await screen.findByText(/4 tree nodes/);
    const body = apiFetch.mock.calls[0][1].body as FormData;
    expect(body.get("build_tree")).toBe("true");
  });

  it("reports a per-file error without aborting the rest of the queue", async () => {
    apiFetch
      .mockRejectedValueOnce(new Error("file too large"))
      .mockResolvedValueOnce({
        message: "ok",
        chunks_processed: 2,
        vectors_created: 2,
        filename: "b.pdf",
        document_id: "doc-2",
      });
    render(<UploadWidget kb={kb()} token="tok" onUploaded={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/Upload documents/), {
      target: { files: [fakeFile("a.pdf"), fakeFile("b.pdf")] },
    });
    fireEvent.click(screen.getByText("Upload all"));

    await screen.findByText(/a.pdf — error: file too large/);
    await screen.findByText(/b.pdf — done: 2 chunks, 2 vectors/);
  });
});

describe("DocumentsList", () => {
  it("renders nothing until the first load settles", () => {
    apiFetch.mockReturnValue(new Promise(() => {}));
    const { container } = render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={vi.fn()} confirm={vi.fn()} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows an empty state when there are no documents", async () => {
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={vi.fn()} confirm={vi.fn()} />,
    );
    await screen.findByText(/No documents uploaded yet/);
  });

  it("lists documents and shows a distinct error state on fetch failure", async () => {
    apiFetch.mockRejectedValue(new Error("rag-pipeline unreachable"));
    render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={vi.fn()} confirm={vi.fn()} />,
    );
    await screen.findByText("Couldn't load documents — see error below.");
    expect(screen.getByText("rag-pipeline unreachable")).toBeTruthy();
  });

  it("does not delete a document when the confirmation is declined", async () => {
    apiFetch.mockResolvedValue({
      items: [{ document_id: "doc-1", filename: "a.pdf", chunk_count: 3 }],
      total: 1,
      limit: 100,
      offset: 0,
    });
    const confirm = vi.fn().mockResolvedValue(false);
    const onDeleted = vi.fn();
    render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={onDeleted} confirm={confirm} />,
    );
    await screen.findByText(/a.pdf/);

    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());

    expect(apiFetch).toHaveBeenCalledTimes(1); // only the initial list load
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes a document once confirmed and reloads the list", async () => {
    apiFetch
      .mockResolvedValueOnce({
        items: [{ document_id: "doc-1", filename: "a.pdf", chunk_count: 3 }],
        total: 1,
        limit: 100,
        offset: 0,
      })
      .mockResolvedValueOnce({}) // the DELETE call
      .mockResolvedValueOnce({ items: [], total: 0, limit: 100, offset: 0 }); // reload
    const confirm = vi.fn().mockResolvedValue(true);
    const onDeleted = vi.fn();
    render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={onDeleted} confirm={confirm} />,
    );
    await screen.findByText(/a.pdf/);

    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalled());
    expect(apiFetch).toHaveBeenCalledWith(
      "/v1/rag/knowledge-bases/kb-1/documents/doc-1",
      { method: "DELETE", token: "tok" },
    );
  });

  it("shows a friendly error when delete fails", async () => {
    apiFetch
      .mockResolvedValueOnce({
        items: [{ document_id: "doc-1", filename: "a.pdf", chunk_count: 3 }],
        total: 1,
        limit: 100,
        offset: 0,
      })
      .mockRejectedValueOnce(new Error("rag-pipeline unreachable"));
    const confirm = vi.fn().mockResolvedValue(true);
    render(
      <DocumentsList kbId="kb-1" token="tok" refreshToken={0} onDeleted={vi.fn()} confirm={confirm} />,
    );
    await screen.findByText(/a.pdf/);

    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete" }));

    await screen.findByText("rag-pipeline unreachable");
  });
});

describe("KnowledgeBaseCard", () => {
  it("shows a login hint and disables edit/delete when logged out", () => {
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <KnowledgeBaseCard kb={kb()} token="" onDeleted={vi.fn()} onRefresh={vi.fn()} confirm={vi.fn()} />,
    );
    expect(screen.getByText("Log in to edit or delete this knowledge base.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "✏️ Edit" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "🗑 Delete KB" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("rejects an empty name on save", async () => {
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={vi.fn()} onRefresh={vi.fn()} confirm={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Edit" }));
    fireEvent.change(screen.getByLabelText("Knowledge base name"), { target: { value: "  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await screen.findByText("Name can't be empty.");
  });

  it("saves an edit and exits edit mode", async () => {
    apiFetch.mockImplementation((_path: string, opts?: { method?: string }) => {
      if (opts?.method === "PATCH") return Promise.resolve(kb({ name: "Renamed" }));
      return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
    });
    const onRefresh = vi.fn();
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={vi.fn()} onRefresh={onRefresh} confirm={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Edit" }));
    fireEvent.change(screen.getByLabelText("Knowledge base name"), { target: { value: "Renamed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onRefresh).toHaveBeenCalledWith(kb({ name: "Renamed" })));
    expect(screen.queryByLabelText("Knowledge base name")).toBeNull();
  });

  it("cancels an edit without saving", () => {
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={vi.fn()} onRefresh={vi.fn()} confirm={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "✏️ Edit" }));
    fireEvent.change(screen.getByLabelText("Knowledge base name"), { target: { value: "Discard" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByText("Support docs")).toBeTruthy();
  });

  it("does not delete when the confirmation is declined", async () => {
    apiFetch.mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 });
    const confirm = vi.fn().mockResolvedValue(false);
    const onDeleted = vi.fn();
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={onDeleted} onRefresh={vi.fn()} confirm={confirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete KB" }));
    await waitFor(() => expect(confirm).toHaveBeenCalled());

    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("deletes the knowledge base once confirmed", async () => {
    apiFetch.mockImplementation((_path: string, opts?: { method?: string }) => {
      if (opts?.method === "DELETE") return Promise.resolve({});
      return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
    });
    const confirm = vi.fn().mockResolvedValue(true);
    const onDeleted = vi.fn();
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={onDeleted} onRefresh={vi.fn()} confirm={confirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete KB" }));

    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("kb-1"));
  });

  it("shows a friendly error when delete fails", async () => {
    apiFetch.mockImplementation((_path: string, opts?: { method?: string }) => {
      if (opts?.method === "DELETE") return Promise.reject(new Error("rag-pipeline unreachable"));
      return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
    });
    const confirm = vi.fn().mockResolvedValue(true);
    render(
      <KnowledgeBaseCard kb={kb()} token="tok" onDeleted={vi.fn()} onRefresh={vi.fn()} confirm={confirm} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "🗑 Delete KB" }));

    await screen.findByText("rag-pipeline unreachable");
  });
});

describe("CreateKbForm", () => {
  it("requires a name", async () => {
    apiFetch.mockResolvedValue({ items: [] });
    render(<CreateKbForm token="tok" onCreated={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await screen.findByText("Name is required.");
    // The one apiFetch call so far is the background model-list fetch, not a create.
    expect(apiFetch).not.toHaveBeenCalledWith("/v1/rag/knowledge-bases", expect.anything());
  });

  it("creates a knowledge base with only the required fields and resets the form", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      return Promise.resolve(kb());
    });
    const onCreated = vi.fn();
    render(<CreateKbForm token="tok" onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Support docs" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(kb()));
    expect(apiFetch).toHaveBeenCalledWith("/v1/rag/knowledge-bases", {
      method: "POST",
      body: { name: "Support docs" },
      token: "tok",
    });
    expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("");
  });

  it("includes optional fields, parsing chunk size/overlap as numbers", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      return Promise.resolve(kb());
    });
    render(<CreateKbForm token="tok" onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Support docs" } });
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Help articles" } });
    fireEvent.change(screen.getByLabelText("Chunk size"), { target: { value: "512" } });
    fireEvent.change(screen.getByLabelText("Chunk overlap"), { target: { value: "50" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith("/v1/rag/knowledge-bases", {
        method: "POST",
        body: {
          name: "Support docs",
          description: "Help articles",
          chunk_size: 512,
          chunk_overlap: 50,
        },
        token: "tok",
      }),
    );
  });

  it("splits the fetched model list into embedding vs. LLM dropdowns by name", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/models")) {
        return Promise.resolve({
          items: [
            { id: "m1", name: "nomic-embed-text" },
            { id: "m2", name: "llama3" },
          ],
        });
      }
      return Promise.resolve(kb());
    });
    render(<CreateKbForm token="tok" onCreated={vi.fn()} />);

    await screen.findByRole("option", { name: "nomic-embed-text" });
    const embeddingSelect = screen.getByLabelText("Embedding model") as HTMLSelectElement;
    const llmSelect = screen.getByLabelText("LLM model") as HTMLSelectElement;
    expect(
      Array.from(embeddingSelect.options).some((o) => o.value === "llama3"),
    ).toBe(false);
    expect(
      Array.from(llmSelect.options).some((o) => o.value === "nomic-embed-text"),
    ).toBe(false);
    expect(Array.from(llmSelect.options).some((o) => o.value === "llama3")).toBe(true);
  });

  it("degrades gracefully to just the default option when the model list fails to load", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/models")) return Promise.reject(new Error("unreachable"));
      return Promise.resolve(kb());
    });
    render(<CreateKbForm token="tok" onCreated={vi.fn()} />);

    await waitFor(() => expect(apiFetch).toHaveBeenCalled());
    const embeddingSelect = screen.getByLabelText("Embedding model") as HTMLSelectElement;
    expect(embeddingSelect.options.length).toBe(1);
  });

  it("shows a friendly error on create failure", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      return Promise.reject(new Error("rag-pipeline unreachable"));
    });
    render(<CreateKbForm token="tok" onCreated={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Support docs" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await screen.findByText("rag-pipeline unreachable");
  });

  it("shows a login hint and disables submit when logged out", () => {
    apiFetch.mockResolvedValue({ items: [] });
    render(<CreateKbForm token="" onCreated={vi.fn()} />);
    expect(screen.getByText("Log in to create a knowledge base.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Create" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("KnowledgeBasesPage", () => {
  it("loads knowledge bases on mount", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases?")) return Promise.resolve({ items: [kb()] });
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      if (path.startsWith("/v1/rag/knowledge-bases/kb-1/documents")) {
        return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
      }
      throw new Error(`unexpected path ${path}`);
    });
    render(<KnowledgeBasesPage />);

    expect(await screen.findByText("Support docs")).toBeTruthy();
  });

  it("shows an empty state when there are no knowledge bases", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases?")) return Promise.resolve({ items: [] });
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      throw new Error(`unexpected path ${path}`);
    });
    render(<KnowledgeBasesPage />);

    await screen.findByText("No knowledge bases yet — create one above to get started.");
  });

  it("shows a friendly error status when the initial load fails", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases?")) return Promise.reject(new Error("rag-pipeline unreachable"));
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      throw new Error(`unexpected path ${path}`);
    });
    render(<KnowledgeBasesPage />);

    await screen.findByText("rag-pipeline unreachable");
  });

  it("filters knowledge bases by name and shows a no-match empty state", async () => {
    apiFetch.mockImplementation((path: string) => {
      if (path.startsWith("/v1/rag/knowledge-bases?")) {
        return Promise.resolve({
          items: [kb({ id: "kb-1", name: "Support" }), kb({ id: "kb-2", name: "Sales" })],
        });
      }
      if (path.startsWith("/v1/models")) return Promise.resolve({ items: [] });
      if (path.includes("/documents")) return Promise.resolve({ items: [], total: 0, limit: 100, offset: 0 });
      throw new Error(`unexpected path ${path}`);
    });
    render(<KnowledgeBasesPage />);
    await screen.findByText("Support");

    fireEvent.change(screen.getByLabelText("Filter knowledge bases"), { target: { value: "sal" } });
    expect(screen.getByText("Sales")).toBeTruthy();
    expect(screen.queryByText("Support")).toBeNull();
    expect(screen.getByText("1 of 2")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Filter knowledge bases"), { target: { value: "nope" } });
    await screen.findByText('No knowledge bases match "nope".');
  });
});
