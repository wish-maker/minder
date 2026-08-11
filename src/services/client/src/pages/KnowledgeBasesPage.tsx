import { useCallback, useEffect, useId, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { PageHeader } from "../components/PageHeader";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
  statusClass,
} from "../lib/ui";

interface ModelInfo {
  id: string;
  name: string;
}

const fieldHintClass = "mt-0.5 text-xs text-gray-500 dark:text-gray-400";

interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  embedding_model: string;
  llm_model: string;
  document_count: number;
  vector_count: number;
  created_at: string;
}

interface UploadResponse {
  message: string;
  chunks_processed: number;
  vectors_created: number;
  filename: string;
  document_id: string;
}

interface KbDocument {
  document_id: string;
  filename: string;
  chunk_count: number;
  uploaded_at?: string;
}

interface QueueItem {
  file: File;
  status: "queued" | "uploading" | "done" | "error";
  detail: string;
}

function UploadWidget({
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
      try {
        const res = await apiFetch<UploadResponse>(
          `/v1/rag/knowledge-bases/${kb.id}/upload`,
          { method: "POST", body: form, token },
        );
        setQueue((q) =>
          q.map((item, idx) =>
            idx === i
              ? {
                  ...item,
                  status: "done",
                  detail: `${res.chunks_processed} chunks, ${res.vectors_created} vectors`,
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

function DocumentsList({
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
  const [docs, setDocs] = useState<KbDocument[] | null>(null);
  const [status, setStatus] = useState("");
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    setLoadError(false);
    apiFetch<KbDocument[]>(`/v1/rag/knowledge-bases/${kbId}/documents`)
      .then(setDocs)
      .catch((e) => {
        // A real fetch failure must not render as "no documents" -- that's
        // indistinguishable from a genuinely empty KB and hides the actual
        // error (e.g. an expired session) from the user entirely.
        setDocs([]);
        setLoadError(true);
        setStatus(friendlyErrorMessage(e));
      });
  }, [kbId, refreshToken]);

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
      setDocs((prev) => (prev ?? []).filter((d) => d.document_id !== doc.document_id));
      setStatus("");
      onDeleted();
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
  }

  if (docs === null) return null;

  return (
    <div>
      <h3 className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
        Documents
      </h3>
      {docs.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {loadError
            ? "Couldn't load documents — see error below."
            : "No documents uploaded yet — use the upload field below."}
        </p>
      ) : (
        <ul className="flex flex-col gap-1.5">
          {docs.map((d) => (
            <li
              key={d.document_id}
              className="flex items-center justify-between gap-3 rounded-md bg-gray-50 px-3 py-1.5 text-sm dark:bg-gray-800"
            >
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
            </li>
          ))}
        </ul>
      )}
      <div className={statusClass(loadError)}>{status}</div>
    </div>
  );
}

function KnowledgeBaseCard({
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
        <button
          className={destructiveButtonClass}
          onClick={handleDelete}
          disabled={!token}
        >
          🗑 Delete KB
        </button>
      </div>
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to delete this knowledge base.
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
      <div className={statusClass(false)}>{status}</div>
    </section>
  );
}

function CreateKbForm({
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

  useEffect(() => {
    // Free-text model-name inputs made a user guess/copy-paste an exact
    // Ollama model string with zero validation, when the platform already
    // knows exactly which models are pulled (ModelManagementPage's own data
    // source) -- offer that list instead. Best-effort: an empty list just
    // means every dropdown falls back to its single "(server default)"
    // option, same as before this existed.
    apiFetch<ModelInfo[]>("/v1/models")
      .then(setModels)
      .catch(() => {});
  }, []);

  const embeddingModels = models.filter((m) => /embed/i.test(m.name));
  const llmModels = models.filter((m) => !/embed/i.test(m.name));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
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
    }
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-3 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">➕</span> Create a knowledge base
      </h2>
      <form onSubmit={handleSubmit}>
        <fieldset
          disabled={!token}
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
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const loadKbs = useCallback(async () => {
    setStatusMsg("Loading knowledge bases…");
    try {
      const list = await apiFetch<KnowledgeBase[]>("/v1/rag/knowledge-bases?limit=100");
      setKbs(list);
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
      <div className={statusClass(isError)}>{status}</div>
      <CreateKbForm
        token={token}
        onCreated={(kb) => setKbs((prev) => [...(prev ?? []), kb])}
      />
      {kbs !== null && kbs.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No knowledge bases yet — create one above to get started.
        </p>
      )}
      {kbs?.map((kb) => (
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
