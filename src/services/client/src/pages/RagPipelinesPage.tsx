import { useCallback, useEffect, useState } from "react";

import { LoginPanel } from "../components/LoginPanel";
import { ApiError, apiFetch } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  addPipeline,
  loadPipelines,
  removePipeline,
  type TrackedPipeline,
} from "../lib/pipelineStore";

interface KnowledgeBase {
  id: string;
  name: string;
}

interface Capabilities {
  methods: {
    standard: boolean;
    conversational: boolean;
    hyde: boolean;
    self_rag: boolean;
    auto: boolean;
    corrective: boolean;
  };
  enhancers: {
    rerank: { available: boolean; backend?: string };
    compress: { available: boolean };
  };
  retrievers: {
    dense: { available: boolean };
    hybrid: { available: boolean };
    parent_child: { available: boolean; note?: string };
  };
}

type Method = "standard" | "hyde" | "self_rag" | "auto" | "corrective";

interface Source {
  text: string;
  source: string;
  score: number;
}

interface QueryResponse {
  answer: string;
  sources: Source[];
  confidence: number;
  model_used: string;
  tokens_used?: number | null;
  method: string;
  method_details?: { retrieval: string; degraded?: string[] } | null;
}

function CreatePipelineForm({
  token,
  kbs,
  onCreated,
}: {
  token: string;
  kbs: KnowledgeBase[];
  onCreated: (p: TrackedPipeline) => void;
}) {
  const [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [status, setStatus] = useState("");

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setStatus("Name is required.");
      return;
    }
    if (selected.size === 0) {
      setStatus("Pick at least one knowledge base.");
      return;
    }
    setStatus("Creating…");
    try {
      const res = await apiFetch<{
        pipeline_id: string;
        name: string;
        knowledge_base_ids: string[];
        created_at: string;
      }>("/v1/rag/pipeline", {
        method: "POST",
        body: { name, knowledge_base_ids: Array.from(selected) },
        token,
      });
      onCreated({
        id: res.pipeline_id,
        name: res.name,
        knowledge_base_ids: res.knowledge_base_ids,
        created_at: res.created_at,
      });
      setName("");
      setSelected(new Set());
      setStatus("Created.");
      setTimeout(() => setStatus(""), 2000);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="plugin-card">
      <h2>Create a pipeline</h2>
      {kbs.length === 0 ? (
        <p className="hint">Create a knowledge base first.</p>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="field">
            <label>Name</label>
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="field">
            <label>Knowledge bases</label>
            {kbs.map((kb) => (
              <div key={kb.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(kb.id)}
                    onChange={() => toggle(kb.id)}
                  />{" "}
                  {kb.name}
                </label>
              </div>
            ))}
          </div>
          <button type="submit" disabled={!token}>
            Create
          </button>
          {!token && <span className="hint"> Log in to create a pipeline.</span>}
          <div className="status">{status}</div>
        </form>
      )}
    </section>
  );
}

function QueryPanel({
  pipelineId,
  token,
  capabilities,
  onGone,
}: {
  pipelineId: string;
  token: string;
  capabilities: Capabilities | null;
  onGone: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState("5");
  const [method, setMethod] = useState<Method>("standard");
  const [rerank, setRerank] = useState(false);
  const [compress, setCompress] = useState(false);
  const [hybrid, setHybrid] = useState(false);
  const [parentContext, setParentContext] = useState(false);
  const [continueConversation, setContinueConversation] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);

  const methodAvailable = (m: Method) => capabilities?.methods[m] !== false;
  const rerankAvailable = capabilities?.enhancers.rerank.available ?? false;
  const compressAvailable = capabilities?.enhancers.compress.available ?? false;
  const hybridAvailable = capabilities?.retrievers.hybrid.available ?? false;
  const conversationalAvailable = capabilities?.methods.conversational ?? false;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) {
      setStatus("Question is required.");
      return;
    }
    let convId = conversationId;
    if (continueConversation && !convId) {
      convId = crypto.randomUUID();
      setConversationId(convId);
    }
    setStatus("Querying…");
    setResult(null);
    try {
      const body: Record<string, unknown> = {
        question,
        top_k: parseInt(topK, 10) || 5,
        method,
        rerank,
        compress,
        hybrid: parentContext ? false : hybrid,
        parent_context: parentContext,
      };
      if (continueConversation && convId) body.conversation_id = convId;
      const res = await apiFetch<QueryResponse>(
        `/v1/rag/pipeline/${pipelineId}/query`,
        { method: "POST", body, token },
      );
      setResult(res);
      setStatus("");
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setStatus("This pipeline no longer exists on the server — removed from your list.");
        onGone();
        return;
      }
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="field">
      <h3>Query</h3>
      <form onSubmit={handleSubmit}>
        <div className="field">
          <label>Question</label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>
        <div className="field">
          <label>Top K</label>
          <input
            type="number"
            value={topK}
            onChange={(e) => setTopK(e.target.value)}
          />
        </div>
        <div className="field">
          <label>Method</label>
          <select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
            <option value="standard">standard</option>
            <option value="hyde" disabled={!methodAvailable("hyde")}>
              hyde{!methodAvailable("hyde") && " (unavailable on this host)"}
            </option>
            <option value="self_rag" disabled={!methodAvailable("self_rag")}>
              self_rag{!methodAvailable("self_rag") && " (unavailable on this host)"}
            </option>
            <option value="auto" disabled={!methodAvailable("auto")}>
              auto{!methodAvailable("auto") && " (unavailable on this host)"}
            </option>
            <option value="corrective" disabled={!methodAvailable("corrective")}>
              corrective{!methodAvailable("corrective") && " (unavailable on this host)"}
            </option>
          </select>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={rerank}
              disabled={!rerankAvailable}
              onChange={(e) => setRerank(e.target.checked)}
            />{" "}
            Rerank
            {rerankAvailable
              ? capabilities?.enhancers.rerank.backend &&
                ` (${capabilities.enhancers.rerank.backend})`
              : " (unavailable on this host)"}
          </label>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={compress}
              disabled={!compressAvailable}
              onChange={(e) => setCompress(e.target.checked)}
            />{" "}
            Compress{!compressAvailable && " (unavailable on this host)"}
          </label>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={hybrid}
              disabled={!hybridAvailable || parentContext}
              onChange={(e) => setHybrid(e.target.checked)}
            />{" "}
            Hybrid retrieval
            {!hybridAvailable && " (unavailable on this host)"}
            {hybridAvailable && parentContext && " (ignored while parent context is on)"}
          </label>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={parentContext}
              onChange={(e) => setParentContext(e.target.checked)}
            />{" "}
            Parent context retrieval
          </label>
          {capabilities?.retrievers.parent_child.note && (
            <p className="hint">{capabilities.retrievers.parent_child.note}</p>
          )}
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={continueConversation}
              disabled={!conversationalAvailable}
              onChange={(e) => {
                setContinueConversation(e.target.checked);
                if (!e.target.checked) setConversationId(null);
              }}
            />{" "}
            Continue conversation
            {!conversationalAvailable && " (unavailable on this host)"}
          </label>
        </div>
        <button type="submit" disabled={!token}>
          Ask
        </button>
        {!token && <span className="hint"> Log in to query.</span>}
        <div className="status">{status}</div>
      </form>
      {result && (
        <div className="test-result">
          <strong>Answer:</strong> {result.answer}
          {"\n\n"}
          <strong>Confidence:</strong> {Math.round(result.confidence * 100)}%{"\n"}
          <strong>Model:</strong> {result.model_used}
          {result.tokens_used != null && ` (${result.tokens_used} tokens)`}
          {"\n"}
          <strong>Method:</strong> {result.method}
          {result.method_details?.retrieval && ` (${result.method_details.retrieval} retrieval)`}
          {result.method_details?.degraded && result.method_details.degraded.length > 0 && (
            <>
              {"\n"}
              <strong>Degraded:</strong> {result.method_details.degraded.join(", ")}
            </>
          )}
          {result.sources.length > 0 && (
            <>
              {"\n\n"}
              <strong>Sources:</strong>
              {result.sources.map((s, i) => (
                <div key={i}>
                  {"\n"}[{s.source}] score {s.score.toFixed(3)} — {s.text.slice(0, 200)}
                  {s.text.length > 200 && "…"}
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function PipelineCard({
  pipeline,
  token,
  capabilities,
  onDeleted,
}: {
  pipeline: TrackedPipeline;
  token: string;
  capabilities: Capabilities | null;
  onDeleted: (id: string) => void;
}) {
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleDelete() {
    if (!confirm(`Delete pipeline "${pipeline.name}"? This cannot be undone.`)) return;
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/rag/pipeline/${pipeline.id}`, { method: "DELETE", token });
      onDeleted(pipeline.id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setStatus("This pipeline no longer exists on the server — removed from your list.");
        onDeleted(pipeline.id);
        return;
      }
      setStatus(e instanceof Error ? e.message : String(e));
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(pipeline.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className="plugin-card">
      <h2>{pipeline.name}</h2>
      <p className="hint">
        id: <code>{pipeline.id}</code>{" "}
        <button type="button" onClick={handleCopy}>
          {copied ? "Copied" : "Copy"}
        </button>
      </p>
      <p className="hint">
        Knowledge bases: {pipeline.knowledge_base_ids.join(", ")}
      </p>
      <button className="danger" onClick={handleDelete} disabled={!token}>
        Delete
      </button>
      {!token && <span className="hint"> Log in to delete.</span>}
      <div className="status">{status}</div>
      <QueryPanel
        pipelineId={pipeline.id}
        token={token}
        capabilities={capabilities}
        onGone={() => onDeleted(pipeline.id)}
      />
    </section>
  );
}

export function RagPipelinesPage() {
  const { token, username } = useAuth();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [pipelines, setPipelines] = useState<TrackedPipeline[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const load = useCallback(async () => {
    setStatusMsg("Loading…");
    try {
      const [kbList, caps] = await Promise.all([
        apiFetch<KnowledgeBase[]>("/v1/rag/knowledge-bases?limit=100"),
        apiFetch<Capabilities>("/v1/rag/capabilities"),
      ]);
      setKbs(kbList);
      setCapabilities(caps);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(e instanceof Error ? e.message : String(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPipelines(username ? loadPipelines(username) : []);
  }, [username]);

  function handlePipelineDeleted(id: string) {
    if (!username) return;
    setPipelines(removePipeline(username, id));
  }

  return (
    <>
      <h1>RAG Pipelines</h1>
      <p className="hint">
        Build a pipeline over one or more knowledge bases and query it using
        Minder's own RAG pipeline (standard, HyDE, Self-RAG, auto, or
        corrective retrieval) — this is separate from OpenWebUI's own
        disconnected Knowledge feature.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={`status${isError ? " error" : ""}`}>{status}</div>
      <CreatePipelineForm
        token={token}
        kbs={kbs}
        onCreated={(p) => {
          if (!username) return;
          setPipelines(addPipeline(username, p));
        }}
      />
      {pipelines.length === 0 && (
        <p>No pipelines created yet — pick at least one knowledge base above.</p>
      )}
      {pipelines.map((p) => (
        <PipelineCard
          key={p.id}
          pipeline={p}
          token={token}
          capabilities={capabilities}
          onDeleted={handlePipelineDeleted}
        />
      ))}
    </>
  );
}
