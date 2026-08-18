import { useCallback, useEffect, useId, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import type { Paginated } from "../lib/api";
import { filterByText } from "../lib/filterByText";
import { useAsyncResource } from "../lib/useAsyncResource";
import { useAuth } from "../lib/auth";
import {
  cardClass,
  destructiveButtonClass,
  fieldHintClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";
import { EmptyState } from "../components/EmptyState";

export interface ModelInfo {
  id: string;
  name: string;
}

export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model: string;
  llm_model: string;
  document_count: number;
  vector_count: number;
  created_at: string;
}

export interface UploadResponse {
  message: string;
  chunks_processed: number;
  vectors_created: number;
  filename: string;
  document_id: string;
  tree_nodes_created?: number;
}

export interface KbDocument {
  document_id: string;
  filename: string;
  chunk_count: number;
  uploaded_at?: string;
}

export interface ChunkInfo {
  chunk_index: number;
  text: string;
}

/** Lazily fetches a document's stored chunk text on first expand -- lets a
 * user tell a bad extraction/OCR (garbled or missing text) apart from a
 * retrieval/generation issue, which previously had no diagnostic short of
 * trial-and-error querying. Same lazy-expand-on-first-open pattern as
 * ConfigurePanel (InstalledPluginsPage) / ModelDetailPanel (ModelManagementPage). */
export function ChunkViewer({
  kbId,
  documentId,
}: {
  kbId: string;
  documentId: string;
}) {
  const [loaded, setLoaded] = useState(false);
  const [chunks, setChunks] = useState<ChunkInfo[]>([]);
  const [status, setStatus] = useState("");

  async function handleToggle(e: React.SyntheticEvent<HTMLDetailsElement>) {
    if (!e.currentTarget.open || loaded) return;
    setStatus("Loading…");
    try {
      // 500 (the max page size the backend allows) rather than paginating in
      // the UI -- a document with more chunks than that is a rare edge case
      // not worth building pagination controls for in a first version.
      const res = await apiFetch<Paginated<ChunkInfo>>(
        `/v1/rag/knowledge-bases/${kbId}/documents/${documentId}/chunks?limit=500`,
      );
      setChunks(res.items);
      setLoaded(true);
      setStatus("");
    } catch (err) {
      setStatus(friendlyErrorMessage(err));
    }
  }

  return (
    <details className="mt-1.5" onToggle={handleToggle}>
      <summary className="cursor-pointer text-xs font-medium text-indigo-600 dark:text-indigo-400">
        View chunks
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        {status && (
          <p className="text-xs text-gray-500 dark:text-gray-400">{status}</p>
        )}
        {loaded &&
          chunks.map((c) => (
            <div
              key={c.chunk_index}
              className="rounded-md bg-white p-2 text-xs dark:bg-gray-900"
            >
              <div className="mb-1 font-mono text-gray-400 dark:text-gray-500">
                #{c.chunk_index}
              </div>
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-sans text-gray-700 dark:text-gray-300">
                {c.text}
              </pre>
            </div>
          ))}
      </div>
    </details>
  );
}

interface QueueItem {
  file: File;
  status: "queued" | "uploading" | "done" | "error";
  detail: string;
}

export function UploadWidget({
  kb,
  token,
  onUploaded,
}: {
  kb: KnowledgeBase;
  token: string;
  onUploaded: () => void;
}) {
  const fileInputId = useId();
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [buildTree, setBuildTree] = useState(false);

  function handleSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    setQueue(files.map((file) => ({ file, status: "queued", detail: "" })));
    e.target.value = "";
  }

  async function handleUploadAll() {
    setUploading(true);
    for (let i = 0; i < queue.length; i++) {
      setQueue((q) =>
        q.map((item, idx) => (idx === i ? { ...item, status: "uploading" } : item)),
      );
      const form = new FormData();
      form.append("file", queue[i].file);
      if (buildTree) form.append("build_tree", "true");
      try {
        const res = await apiFetch<UploadResponse>(
          `/v1/rag/knowledge-bases/${kb.id}/upload`,
          { method: "POST", body: form, token },
        );
        const treeNote = res.tree_nodes_created
          ? `, ${res.tree_nodes_created} tree nodes`
          : "";
        setQueue((q) =>
          q.map((item, idx) =>
            idx === i
              ? {
                  ...item,
                  status: "done",
                  detail: `${res.chunks_processed} chunks, ${res.vectors_created} vectors${treeNote}`,
                }
              : item,
          ),
        );
      } catch (e) {
        setQueue((q) =>
          q.map((item, idx) =>
            idx === i
              ? { ...item, status: "error", detail: friendlyErrorMessage(e) }
              : item,
          ),
        );
      }
    }
    setUploading(false);
    onUploaded();
  }

  return (
    <div className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800">
      <label
        htmlFor={fileInputId}
        className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
      >
        Upload documents (.pdf, .txt, .md)
      </label>
      <input
        id={fileInputId}
        className="block text-sm text-gray-600 disabled:cursor-not-allowed disabled:opacity-60 dark:text-gray-400"
        type="file"
        multiple
        accept=".pdf,.txt,.md"
        onChange={handleSelect}
        disabled={!token || uploading}
      />
      <label className="mt-2 flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
          checked={buildTree}
          onChange={(e) => setBuildTree(e.target.checked)}
          disabled={!token || uploading}
        />
        Build search tree (RAPTOR, experimental) — clusters and summarizes this
        upload so the "raptor" query method can search summaries as well as raw
        chunks; adds extra processing time per upload.
      </label>
      {queue.length > 0 && (
        <>
          <ul className="mt-2 flex flex-col gap-1 text-sm text-gray-600 dark:text-gray-400">
            {queue.map((item, idx) => (
              <li key={idx}>
                {item.file.name} — {item.status}
                {item.detail && `: ${item.detail}`}
              </li>
            ))}
          </ul>
          <button
            onClick={handleUploadAll}
            disabled={!token || uploading}
            className={`${secondaryButtonClass} mt-2`}
          >
            {uploading ? "Uploading…" : "Upload all"}
          </button>
        </>
      )}
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to upload documents.
        </p>
      )}
    </div>
  );
}

export function DocumentsList({
  kbId,
  token,
  refreshToken,
  onDeleted,
  confirm,
}: {
  kbId: string;
  token: string;
  refreshToken: number;
  onDeleted: () => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");

  // Re-fetches whenever the selected KB (or an upload's refreshToken) changes.
  // The hook's stale-response guard is what matters here: clicking KB A then
  // quickly KB B previously raced two /documents loads, and if A resolved last
  // it showed A's documents under B. Now the superseded response is dropped.
  // (#502) A real fetch failure surfaces as `error`, never as an empty list —
  // "no documents" would be indistinguishable from a genuinely empty KB.
  const docsRes = useAsyncResource(
    (signal) =>
      apiFetch<Paginated<KbDocument>>(
        `/v1/rag/knowledge-bases/${kbId}/documents`,
        { signal },
      ).then((res) => res.items),
    { deps: [kbId, refreshToken] },
  );

  async function handleDelete(doc: KbDocument) {
    const ok = await confirm({
      title: "Delete document?",
      message: `This permanently removes "${doc.filename}" and its ${doc.chunk_count} chunk${doc.chunk_count === 1 ? "" : "s"} from this knowledge base.`,
      danger: true,
    });
    if (!ok) return;
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/rag/knowledge-bases/${kbId}/documents/${doc.document_id}`, {
        method: "DELETE",
        token,
      });
      setStatus("");
      onDeleted();
      docsRes.reload();
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }

  // Don't render the section until the first load settles (data or error) --
  // avoids a flash of "no documents" before the fetch returns.
  if (docsRes.data === null && !docsRes.error) return null;

  const docs = docsRes.data ?? [];

  return (
    <div>
      <h3 className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
        Documents
      </h3>
      {docs.length === 0 ? (
        <EmptyState>
          {docsRes.error
            ? "Couldn't load documents — see error below."
            : "No documents uploaded yet — use the upload field below."}
        </EmptyState>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {docs.map((d) => (
            <li
              key={d.document_id}
              className="rounded-md bg-gray-50 px-3 py-1.5 text-sm dark:bg-gray-800"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="truncate">
                  📄 {d.filename} —{" "}
                  <span className="text-gray-500 dark:text-gray-400">
                    {d.chunk_count} chunk{d.chunk_count === 1 ? "" : "s"}
                  </span>
                </span>
                <button
                  onClick={() => handleDelete(d)}
                  disabled={!token}
                  className={destructiveButtonClass}
                >
                  🗑 Delete
                </button>
              </div>
              <ChunkViewer kbId={kbId} documentId={d.document_id} />
            </li>
          ))}
        </ul>
      )}
      <StatusLine isError={!!docsRes.error}>{docsRes.error ?? status}</StatusLine>
    </div>
  );
}

export function KnowledgeBaseCard({
  kb,
  token,
  onDeleted,
  onRefresh,
  confirm,
}: {
  kb: KnowledgeBase;
  token: string;
  onDeleted: (id: string) => void;
  onRefresh: (kb: KnowledgeBase) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");
  const [docsVersion, setDocsVersion] = useState(0);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(kb.name);
  const [editDesc, setEditDesc] = useState(kb.description);
  const [saving, setSaving] = useState(false);

  function startEdit() {
    setEditName(kb.name);
    setEditDesc(kb.description);
    setStatus("");
    setEditing(true);
  }

  async function handleSaveEdit() {
    if (!editName.trim()) {
      setStatus("Name can't be empty.");
      return;
    }
    setSaving(true);
    setStatus("Saving…");
    try {
      // Metadata-only edit — does NOT touch the documents/vectors (unlike
      // delete + recreate, which drops the whole collection).
      const updated = await apiFetch<KnowledgeBase>(
        `/v1/rag/knowledge-bases/${kb.id}`,
        { method: "PATCH", body: { name: editName.trim(), description: editDesc }, token },
      );
      onRefresh(updated);
      setStatus("");
      setEditing(false);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setSaving(false);
  }

  async function handleDelete() {
    const ok = await confirm({
      title: "Delete knowledge base?",
      message: `This permanently deletes "${kb.name}" and all ${kb.document_count} of its documents. This cannot be undone.`,
      danger: true,
    });
    if (!ok) return;
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/rag/knowledge-bases/${kb.id}`, { method: "DELETE", token });
      onDeleted(kb.id);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }

  async function refreshCounts() {
    try {
      const fresh = await apiFetch<KnowledgeBase>(`/v1/rag/knowledge-bases/${kb.id}`);
      onRefresh(fresh);
    } catch {
      // best-effort refresh -- stale counts are harmless, leave as-is
    }
    setDocsVersion((v) => v + 1);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      {editing ? (
        <div className="flex flex-col gap-2">
          <input
            className={inputClass}
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            placeholder="Name"
            aria-label="Knowledge base name"
            disabled={saving}
          />
          <input
            className={inputClass}
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            placeholder="Description (optional)"
            aria-label="Knowledge base description"
            disabled={saving}
          />
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Editing name/description only — documents and vectors are untouched.
          </p>
          <div className="flex gap-2">
            <button
              className={primaryButtonClass}
              onClick={handleSaveEdit}
              disabled={saving}
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              className={secondaryButtonClass}
              onClick={() => setEditing(false)}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              <span aria-hidden="true">📚</span> {kb.name}
            </h2>
            {kb.description && (
              <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
                {kb.description}
              </p>
            )}
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {kb.document_count} document{kb.document_count === 1 ? "" : "s"} ·{" "}
              {kb.vector_count} vectors · embedding: {kb.embedding_model} · llm:{" "}
              {kb.llm_model}
            </p>
          </div>
          <div className="flex shrink-0 gap-2">
            <button
              className={secondaryButtonClass}
              onClick={startEdit}
              disabled={!token}
            >
              ✏️ Edit
            </button>
            <button
              className={destructiveButtonClass}
              onClick={handleDelete}
              disabled={!token}
            >
              🗑 Delete KB
            </button>
          </div>
        </div>
      )}
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to edit or delete this knowledge base.
        </p>
      )}
      <div className="mt-3 flex flex-col gap-3">
        <DocumentsList
          kbId={kb.id}
          token={token}
          refreshToken={docsVersion}
          onDeleted={refreshCounts}
          confirm={confirm}
        />
        <UploadWidget kb={kb} token={token} onUploaded={refreshCounts} />
      </div>
      <StatusLine isError={false}>{status}</StatusLine>
    </section>
  );
}

export function CreateKbForm({
  token,
  onCreated,
}: {
  token: string;
  onCreated: (kb: KnowledgeBase) => void;
}) {
  const nameId = useId();
  const descriptionId = useId();
  const embeddingModelId = useId();
  const llmModelId = useId();
  const chunkSizeId = useId();
  const chunkOverlapId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [chunkSize, setChunkSize] = useState("");
  const [chunkOverlap, setChunkOverlap] = useState("");
  const [status, setStatus] = useState("");
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    // Free-text model-name inputs made a user guess/copy-paste an exact
    // Ollama model string with zero validation, when the platform already
    // knows exactly which models are pulled (ModelManagementPage's own data
    // source) -- offer that list instead. Best-effort: an empty list just
    // means every dropdown falls back to its single "(server default)"
    // option, same as before this existed.
    apiFetch<Paginated<ModelInfo>>("/v1/models?limit=500")
      .then((res) => setModels(res.items))
      .catch(() => {});
  }, []);

  const embeddingModels = models.filter((m) => /embed/i.test(m.name));
  const llmModels = models.filter((m) => !/embed/i.test(m.name));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (creating) return; // already in flight -- ignore a double-click/tap
    if (!name.trim()) {
      setStatus("Name is required.");
      return;
    }
    const body: Record<string, unknown> = { name };
    if (description) body.description = description;
    if (embeddingModel) body.embedding_model = embeddingModel;
    if (llmModel) body.llm_model = llmModel;
    if (chunkSize) body.chunk_size = parseInt(chunkSize, 10);
    if (chunkOverlap) body.chunk_overlap = parseInt(chunkOverlap, 10);

    setCreating(true);
    setStatus("Creating…");
    try {
      const kb = await apiFetch<KnowledgeBase>("/v1/rag/knowledge-bases", {
        method: "POST",
        body,
        token,
      });
      onCreated(kb);
      setName("");
      setDescription("");
      setEmbeddingModel("");
      setLlmModel("");
      setChunkSize("");
      setChunkOverlap("");
      setStatus("Created.");
      setTimeout(() => setStatus(""), 2000);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-3 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">➕</span> Create a knowledge base
      </h2>
      <form onSubmit={handleSubmit}>
        <fieldset
          disabled={!token || creating}
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
        >
          <div className="sm:col-span-2">
            <label
              htmlFor={nameId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Name
            </label>
            <input
              id={nameId}
              className={inputClass}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="sm:col-span-2">
            <label
              htmlFor={descriptionId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Description
            </label>
            <input
              id={descriptionId}
              className={inputClass}
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div>
            <label
              htmlFor={embeddingModelId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Embedding model
            </label>
            <select
              id={embeddingModelId}
              className={inputClass}
              value={embeddingModel}
              onChange={(e) => setEmbeddingModel(e.target.value)}
            >
              <option value="">(server default)</option>
              {embeddingModels.map((m) => (
                <option key={m.id} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            <p className={fieldHintClass}>
              Turns each chunk of text into a vector for similarity search —
              pick a model whose name contains "embed".
            </p>
          </div>
          <div>
            <label
              htmlFor={llmModelId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              LLM model
            </label>
            <select
              id={llmModelId}
              className={inputClass}
              value={llmModel}
              onChange={(e) => setLlmModel(e.target.value)}
            >
              <option value="">(server default)</option>
              {llmModels.map((m) => (
                <option key={m.id} value={m.name}>
                  {m.name}
                </option>
              ))}
            </select>
            <p className={fieldHintClass}>
              Generates the actual answer from retrieved chunks when this KB
              is queried through a RAG Pipeline.
            </p>
          </div>
          <div>
            <label
              htmlFor={chunkSizeId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Chunk size
            </label>
            <input
              id={chunkSizeId}
              className={inputClass}
              type="number"
              placeholder="512"
              value={chunkSize}
              onChange={(e) => setChunkSize(e.target.value)}
            />
            <p className={fieldHintClass}>
              How much text (in characters) goes into each retrievable piece
              — smaller finds more precise matches, larger keeps more
              surrounding context per match.
            </p>
          </div>
          <div>
            <label
              htmlFor={chunkOverlapId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Chunk overlap
            </label>
            <input
              id={chunkOverlapId}
              className={inputClass}
              type="number"
              placeholder="50"
              value={chunkOverlap}
              onChange={(e) => setChunkOverlap(e.target.value)}
            />
            <p className={fieldHintClass}>
              How many characters consecutive chunks share, so a fact split
              across a chunk boundary still appears whole in at least one.
            </p>
          </div>
          <div className="flex items-center gap-3 sm:col-span-2">
            <button type="submit" disabled={!token} className={primaryButtonClass}>
              Create
            </button>
            {!token && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Log in to create a knowledge base.
              </span>
            )}
            <span className="text-sm text-gray-500 dark:text-gray-400">{status}</span>
          </div>
        </fieldset>
      </form>
    </section>
  );
}

export function KnowledgeBasesPage() {
  const { token } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [kbs, setKbs] = useState<KnowledgeBase[] | null>(null);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const visibleKbs = filterByText(kbs ?? [], filter, (k) => [
    k.name,
    k.description,
  ]);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadKbs = useCallback(async () => {
    setStatusMsg("Loading knowledge bases…");
    try {
      const list = await apiFetch<Paginated<KnowledgeBase>>(
        "/v1/rag/knowledge-bases?limit=100",
      );
      setKbs(list.items);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(friendlyErrorMessage(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    loadKbs();
  }, [loadKbs]);

  return (
    <>
      {dialog}
      <PageHeader icon="📚" title="Knowledge Bases" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Create knowledge bases and upload documents — this is the data your{" "}
        <em>RAG Pipelines</em> actually search over. Browsing is open for
        everyone; log in to create, upload, or delete.
      </p>
      <StatusLine isError={isError}>{status}</StatusLine>
      <CreateKbForm
        token={token}
        onCreated={(kb) => setKbs((prev) => [...(prev ?? []), kb])}
      />
      {kbs !== null && kbs.length === 0 && (
        <EmptyState>
          No knowledge bases yet — create one above to get started.
        </EmptyState>
      )}
      {kbs !== null && kbs.length > 1 && (
        <div className="mb-3 flex items-center gap-3">
          <input
            className={`${inputClass} max-w-xs`}
            type="text"
            placeholder="Filter by name or description…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter knowledge bases"
          />
          {filter.trim() && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {visibleKbs.length} of {kbs.length}
            </span>
          )}
        </div>
      )}
      {kbs !== null && kbs.length > 0 && visibleKbs.length === 0 && (
        <EmptyState>No knowledge bases match "{filter}".</EmptyState>
      )}
      {visibleKbs.map((kb) => (
        <KnowledgeBaseCard
          key={kb.id}
          kb={kb}
          token={token}
          onDeleted={(id) => setKbs((prev) => (prev ?? []).filter((k) => k.id !== id))}
          onRefresh={(fresh) =>
            setKbs((prev) => (prev ?? []).map((k) => (k.id === fresh.id ? fresh : k)))
          }
          confirm={confirm}
        />
      ))}
    </>
  );
}
