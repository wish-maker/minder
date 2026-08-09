import { useCallback, useEffect, useState } from "react";

import { LoginPanel } from "../components/LoginPanel";
import { apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";

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
              ? { ...item, status: "error", detail: e instanceof Error ? e.message : String(e) }
              : item,
          ),
        );
      }
    }
    setUploading(false);
    onUploaded();
  }

  return (
    <div className="field">
      <label>Upload documents (.pdf, .txt, .md)</label>
      <input
        type="file"
        multiple
        accept=".pdf,.txt,.md"
        onChange={handleSelect}
        disabled={!token || uploading}
      />
      {queue.length > 0 && (
        <>
          <ul>
            {queue.map((item, idx) => (
              <li key={idx}>
                {item.file.name} — {item.status}
                {item.detail && `: ${item.detail}`}
              </li>
            ))}
          </ul>
          <button onClick={handleUploadAll} disabled={!token || uploading}>
            {uploading ? "Uploading…" : "Upload all"}
          </button>
        </>
      )}
      {!token && <p className="hint">Log in to upload documents.</p>}
    </div>
  );
}

function KnowledgeBaseCard({
  kb,
  token,
  onDeleted,
  onRefresh,
}: {
  kb: KnowledgeBase;
  token: string;
  onDeleted: (id: string) => void;
  onRefresh: (kb: KnowledgeBase) => void;
}) {
  const [status, setStatus] = useState("");

  async function handleDelete() {
    if (!confirm(`Delete knowledge base "${kb.name}"? This cannot be undone.`)) return;
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/rag/knowledge-bases/${kb.id}`, { method: "DELETE", token });
      onDeleted(kb.id);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function refreshCounts() {
    try {
      const fresh = await apiFetch<KnowledgeBase>(`/v1/rag/knowledge-bases/${kb.id}`);
      onRefresh(fresh);
    } catch {
      // best-effort refresh -- stale counts are harmless, leave as-is
    }
  }

  return (
    <section className="plugin-card">
      <h2>{kb.name}</h2>
      {kb.description && <p className="hint">{kb.description}</p>}
      <p className="hint">
        {kb.document_count} document{kb.document_count === 1 ? "" : "s"},{" "}
        {kb.vector_count} vectors · embedding: {kb.embedding_model} · llm: {kb.llm_model}
      </p>
      <UploadWidget kb={kb} token={token} onUploaded={refreshCounts} />
      <button className="danger" onClick={handleDelete} disabled={!token}>
        Delete
      </button>
      {!token && <span className="hint"> Log in to delete.</span>}
      <div className="status">{status}</div>
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
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [chunkSize, setChunkSize] = useState("");
  const [chunkOverlap, setChunkOverlap] = useState("");
  const [status, setStatus] = useState("");

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
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="plugin-card">
      <h2>Create a knowledge base</h2>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Name</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="field">
          <label>Description</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Embedding model</label>
          <input
            type="text"
            placeholder="nomic-embed-text"
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
          />
        </div>
        <div className="field">
          <label>LLM model</label>
          <input
            type="text"
            placeholder="llama3.2"
            value={llmModel}
            onChange={(e) => setLlmModel(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Chunk size</label>
          <input
            type="number"
            placeholder="512"
            value={chunkSize}
            onChange={(e) => setChunkSize(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Chunk overlap</label>
          <input
            type="number"
            placeholder="50"
            value={chunkOverlap}
            onChange={(e) => setChunkOverlap(e.target.value)}
          />
        </div>
        <button type="submit" disabled={!token}>
          Create
        </button>
        {!token && <span className="hint"> Log in to create a knowledge base.</span>}
        <div className="status">{status}</div>
      </form>
    </section>
  );
}

export function KnowledgeBasesPage() {
  const { token } = useAuth();
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
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    loadKbs();
  }, [loadKbs]);

  return (
    <>
      <h1>Knowledge Bases</h1>
      <p className="hint">
        Create knowledge bases and upload documents for Minder's own RAG
        pipeline. Browsing is open; log in to create, upload, or delete.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={`status${isError ? " error" : ""}`}>{status}</div>
      <CreateKbForm
        token={token}
        onCreated={(kb) => setKbs((prev) => [...(prev ?? []), kb])}
      />
      {kbs !== null && kbs.length === 0 && (
        <p>No knowledge bases yet — create one above.</p>
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
        />
      ))}
    </>
  );
}
