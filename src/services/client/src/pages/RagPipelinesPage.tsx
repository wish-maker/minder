import { useCallback, useEffect, useId, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { LoginPanel } from "../components/LoginPanel";
import { ApiError, apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
  statusClass,
} from "../lib/ui";

interface KnowledgeBase {
  id: string;
  name: string;
}

interface RagPipeline {
  id: string;
  name: string;
  knowledge_base_ids: string[];
  created_at: string;
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

const METHOD_DESCRIPTIONS: Record<Method, string> = {
  standard: "Embeds your question and retrieves the closest matching chunks — fast, and the right default for most questions.",
  hyde: "Generates a hypothetical answer first, then searches using THAT instead of your raw question — often finds better matches for short or vaguely-worded questions.",
  self_rag: "Retrieves, then critiques its own retrieval and answer, re-retrieving if the first pass looks weak — slower, but catches cases where the first search missed the point.",
  auto: "Asks a small decision step to pick standard vs. a more expensive method per-question, so you don't have to guess in advance.",
  corrective: "Grades retrieved chunks for relevance before generating, discarding anything off-topic — reduces answers that ramble off irrelevant context.",
};

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

const fieldHintClass = "mt-0.5 text-xs text-gray-500 dark:text-gray-400";

function CreatePipelineForm({
  token,
  kbs,
  onCreated,
}: {
  token: string;
  kbs: KnowledgeBase[];
  onCreated: (p: RagPipeline) => void;
}) {
  const nameId = useId();
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
      setStatus(friendlyErrorMessage(e));
    }
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">➕</span> Create a pipeline
      </h2>
      {kbs.length === 0 ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Create a knowledge base first — a pipeline needs at least one to
          search over.
        </p>
      ) : (
        <form onSubmit={handleSubmit}>
          <fieldset disabled={!token} className="mt-2 flex flex-col gap-3">
            <div>
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
            <fieldset>
              <legend className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                Knowledge bases
              </legend>
              <div className="flex flex-col gap-1">
                {kbs.map((kb) => (
                  <label key={kb.id} className="flex items-center gap-2 text-sm">
                    <input
                      className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                      type="checkbox"
                      checked={selected.has(kb.id)}
                      onChange={() => toggle(kb.id)}
                    />
                    {kb.name}
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex items-center gap-3">
              <button type="submit" disabled={!token} className={primaryButtonClass}>
                Create
              </button>
              {!token && (
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  Log in to create a pipeline.
                </span>
              )}
              <span className="text-sm text-gray-500 dark:text-gray-400">{status}</span>
            </div>
          </fieldset>
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
  const questionId = useId();
  const topKId = useId();
  const methodId = useId();
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
  const advancedActiveCount = [rerank, compress, hybrid, parentContext, continueConversation].filter(
    Boolean,
  ).length;

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
      setStatus(friendlyErrorMessage(e));
    }
  }

  return (
    <div className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-800">
      <h3 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🔎</span> Query
      </h3>
      <form onSubmit={handleSubmit}>
        <fieldset disabled={!token} className="flex flex-col gap-3">
          <div>
            <label
              htmlFor={questionId}
              className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
            >
              Question
            </label>
            <textarea
              id={questionId}
              className={inputClass}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label
                htmlFor={topKId}
                className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Top K
              </label>
              <input
                id={topKId}
                className={inputClass}
                type="number"
                value={topK}
                onChange={(e) => setTopK(e.target.value)}
              />
              <p className={fieldHintClass}>How many chunks to retrieve and hand to the model.</p>
            </div>
            <div>
              <label
                htmlFor={methodId}
                className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
              >
                Method
              </label>
              <select
                id={methodId}
                className={inputClass}
                value={method}
                onChange={(e) => setMethod(e.target.value as Method)}
              >
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
              <p className={fieldHintClass}>{METHOD_DESCRIPTIONS[method]}</p>
            </div>
          </div>

          <details className="rounded-md border border-gray-100 px-3 py-2 dark:border-gray-800">
            <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300">
              Advanced retrieval options
              {advancedActiveCount > 0 && (
                <span className="ml-1.5 text-xs text-indigo-600 dark:text-indigo-400">
                  ({advancedActiveCount} on)
                </span>
              )}
            </summary>
            <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                    type="checkbox"
                    checked={rerank}
                    disabled={!rerankAvailable}
                    onChange={(e) => setRerank(e.target.checked)}
                  />
                  Rerank
                  {rerankAvailable && capabilities?.enhancers.rerank.backend
                    ? ` (${capabilities.enhancers.rerank.backend})`
                    : !rerankAvailable && " (unavailable on this host)"}
                </label>
                <p className={fieldHintClass}>
                  Re-scores retrieved chunks with a dedicated model for higher
                  precision, before generation — costs a bit of latency.
                </p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                    type="checkbox"
                    checked={compress}
                    disabled={!compressAvailable}
                    onChange={(e) => setCompress(e.target.checked)}
                  />
                  Compress{!compressAvailable && " (unavailable on this host)"}
                </label>
                <p className={fieldHintClass}>
                  Trims retrieved chunks down to the sentences actually relevant
                  to your question before they reach the model.
                </p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                    type="checkbox"
                    checked={hybrid}
                    disabled={!hybridAvailable || parentContext}
                    onChange={(e) => setHybrid(e.target.checked)}
                  />
                  Hybrid retrieval
                  {!hybridAvailable && " (unavailable on this host)"}
                  {hybridAvailable && parentContext && " (ignored while parent context is on)"}
                </label>
                <p className={fieldHintClass}>
                  Combines vector similarity with keyword search — catches exact
                  terms, codes, or names that pure embeddings sometimes miss.
                </p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                    type="checkbox"
                    checked={parentContext}
                    onChange={(e) => setParentContext(e.target.checked)}
                  />
                  Parent context retrieval
                </label>
                <p className={fieldHintClass}>
                  {capabilities?.retrievers.parent_child.note ||
                    "Returns the full surrounding section around a match, not just the matched chunk — more context per hit, at the cost of some precision."}
                </p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    className="h-4 w-4 rounded border-gray-300 disabled:cursor-not-allowed disabled:opacity-60"
                    type="checkbox"
                    checked={continueConversation}
                    disabled={!conversationalAvailable}
                    onChange={(e) => {
                      setContinueConversation(e.target.checked);
                      if (!e.target.checked) setConversationId(null);
                    }}
                  />
                  Continue conversation
                  {!conversationalAvailable && " (unavailable on this host)"}
                </label>
                <p className={fieldHintClass}>
                  Keeps follow-up questions in the same session, so the model can
                  resolve references like "it" or "that" back to earlier turns.
                </p>
              </div>
            </div>
          </details>

          <div className="flex items-center gap-3">
            <button type="submit" disabled={!token} className={primaryButtonClass}>
              Ask
            </button>
            {!token && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                Log in to query.
              </span>
            )}
            <span className="text-sm text-gray-500 dark:text-gray-400">{status}</span>
          </div>
        </fieldset>
      </form>
      {result && (
        <div className="mt-3 rounded-lg bg-gray-50 p-4 text-sm dark:bg-gray-800">
          <p className="mb-2 whitespace-pre-wrap">{result.answer}</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Confidence: {Math.round(result.confidence * 100)}% · Model:{" "}
            {result.model_used}
            {result.tokens_used != null && ` (${result.tokens_used} tokens)`} ·
            Method: {result.method}
            {result.method_details?.retrieval &&
              ` (${result.method_details.retrieval} retrieval)`}
          </p>
          {result.method_details?.degraded && result.method_details.degraded.length > 0 && (
            <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
              ⚠ Degraded: {result.method_details.degraded.join(", ")}
            </p>
          )}
          {result.sources.length > 0 && (
            <div className="mt-3 border-t border-gray-200 pt-2 dark:border-gray-700">
              <p className="mb-1 text-xs font-semibold text-gray-600 dark:text-gray-400">
                Sources
              </p>
              <ul className="flex flex-col gap-1">
                {result.sources.map((s, i) => (
                  <li key={i} className="text-xs text-gray-600 dark:text-gray-400">
                    [{s.source}] score {s.score.toFixed(3)} — {s.text.slice(0, 200)}
                    {s.text.length > 200 && "…"}
                  </li>
                ))}
              </ul>
            </div>
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
  confirm,
}: {
  pipeline: RagPipeline;
  token: string;
  capabilities: Capabilities | null;
  onDeleted: (id: string) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);

  async function handleDelete() {
    const ok = await confirm({
      title: "Delete pipeline?",
      message: `This permanently deletes "${pipeline.name}". The knowledge bases it searches over are not affected.`,
      danger: true,
    });
    if (!ok) return;
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
      setStatus(friendlyErrorMessage(e));
    }
  }

  async function handleCopy() {
    await navigator.clipboard.writeText(pipeline.id);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            <span aria-hidden="true">🧠</span> {pipeline.name}
          </h2>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            id: <code>{pipeline.id}</code>{" "}
            <button
              type="button"
              onClick={handleCopy}
              className={`${secondaryButtonClass} ml-1 px-1.5 py-0.5`}
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            Knowledge bases: {pipeline.knowledge_base_ids.join(", ")}
          </p>
        </div>
        <button
          className={destructiveButtonClass}
          onClick={handleDelete}
          disabled={!token}
        >
          🗑 Delete
        </button>
      </div>
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to delete this pipeline.
        </p>
      )}
      <div className={statusClass(false)}>{status}</div>
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
  const { token } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [pipelines, setPipelines] = useState<RagPipeline[]>([]);
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const load = useCallback(async () => {
    setStatusMsg("Loading…");
    try {
      const [kbList, caps, pipelineList] = await Promise.all([
        apiFetch<KnowledgeBase[]>("/v1/rag/knowledge-bases?limit=100"),
        apiFetch<Capabilities>("/v1/rag/capabilities"),
        apiFetch<RagPipeline[]>("/v1/rag/pipeline?limit=100"),
      ]);
      setKbs(kbList);
      setCapabilities(caps);
      setPipelines(pipelineList);
      setStatusMsg("");
    } catch (e) {
      setStatusMsg(friendlyErrorMessage(e), true);
    }
  }, [setStatusMsg]);

  useEffect(() => {
    load();
  }, [load]);

  function handlePipelineDeleted(id: string) {
    setPipelines((prev) => prev.filter((p) => p.id !== id));
  }

  return (
    <>
      {dialog}
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Combine one or more knowledge bases into a queryable pipeline, then
        ask it questions using Minder's own retrieval methods — this is
        separate from OpenWebUI's own disconnected Knowledge feature.
      </p>
      <LoginPanel onStatus={setStatusMsg} />
      <div className={statusClass(isError)}>{status}</div>
      <CreatePipelineForm
        token={token}
        kbs={kbs}
        onCreated={(p) => setPipelines((prev) => [...prev, p])}
      />
      {pipelines.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No pipelines created yet — pick at least one knowledge base above.
        </p>
      )}
      {pipelines.map((p) => (
        <PipelineCard
          key={p.id}
          pipeline={p}
          token={token}
          capabilities={capabilities}
          onDeleted={handlePipelineDeleted}
          confirm={confirm}
        />
      ))}
    </>
  );
}
