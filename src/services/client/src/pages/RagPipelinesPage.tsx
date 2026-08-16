import { useCallback, useEffect, useId, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { ApiError, apiFetch, friendlyErrorMessage } from "../lib/api";
import type { Paginated } from "../lib/api";
import { useAuth } from "../lib/auth";
import { copyText, randomId } from "../lib/browser";
import { filterByText } from "../lib/filterByText";
import {
  badgeClass,
  cardClass,
  confidenceBadgeColor,
  destructiveButtonClass,
  fieldHintClass,
  inputClass,
  mutedTextClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";
import { EmptyState } from "../components/EmptyState";

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

interface DecisionStats {
  available: boolean;
  total_decisions: number;
  strategy_distribution: Record<string, number>;
  complexity_distribution: Record<string, number>;
  avg_confidence: number | null;
}

interface Capabilities {
  methods: {
    standard: boolean;
    conversational: boolean;
    hyde: boolean;
    self_rag: boolean;
    auto: boolean;
    corrective: boolean;
    raptor: boolean;
  };
  enhancers: {
    rerank: { available: boolean; backend?: string };
    compress: { available: boolean };
  };
  retrievers: {
    dense: { available: boolean };
    hybrid: { available: boolean };
    parent_child: { available: boolean; note?: string };
    metadata_filter: { available: boolean; note?: string };
  };
}

type Method = "standard" | "hyde" | "self_rag" | "auto" | "corrective" | "raptor";

const METHOD_DESCRIPTIONS: Record<Method, string> = {
  standard: "Embeds your question and retrieves the closest matching chunks — fast, and the right default for most questions.",
  hyde: "Generates a hypothetical answer first, then searches using THAT instead of your raw question — often finds better matches for short or vaguely-worded questions.",
  self_rag: "Retrieves, then critiques its own retrieval and answer, re-retrieving if the first pass looks weak — slower, but catches cases where the first search missed the point.",
  auto: "Asks a small decision step to pick standard vs. a more expensive method per-question, so you don't have to guess in advance.",
  corrective: "Grades retrieved chunks for relevance before generating, discarding anything off-topic — reduces answers that ramble off irrelevant context.",
  raptor: "Searches across document summaries as well as raw chunks — better for broad \"summarize this\" questions no single chunk answers well. Only searches summaries for documents uploaded with \"Build search tree\" checked; otherwise behaves exactly like standard.",
};

// Same "single source of truth" pattern as METHOD_DESCRIPTIONS above -- these
// used to be inline JSX text duplicated only next to each checkbox, so they
// were invisible unless you already had a pipeline open and expanded
// "Advanced retrieval options". Reused below by the always-visible reference
// section, and by the checkboxes themselves (#485).
const ENHANCER_LABELS: Record<string, string> = {
  rerank: "Rerank",
  compress: "Compress",
  hybrid: "Hybrid retrieval",
  parent_context: "Parent context retrieval",
  continue_conversation: "Continue conversation",
};

const ENHANCER_DESCRIPTIONS: Record<string, string> = {
  rerank: "Re-scores retrieved chunks with a dedicated model for higher precision, before generation — costs a bit of latency.",
  compress: "Trims retrieved chunks down to the sentences actually relevant to your question before they reach the model.",
  hybrid: "Combines vector similarity with keyword search — catches exact terms, codes, or names that pure embeddings sometimes miss.",
  parent_context: "Returns the full surrounding section around a match, not just the matched chunk — more context per hit, at the cost of some precision.",
  continue_conversation: 'Keeps follow-up questions in the same session, so the model can resolve references like "it" or "that" back to earlier turns.',
};

/** Always-visible reference, positioned above the pipeline list/form so a
 * user can learn what these methods and add-ons actually do WITHOUT first
 * creating a knowledge base and a pipeline just to reach the query form
 * that used to be the only place any of this was explained (#485). */
function RetrievalMethodsReference() {
  return (
    <section className={`mb-4 ${cardClass}`}>
      <h2 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
        🔎 Retrieval methods — what they actually do
      </h2>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {(Object.keys(METHOD_DESCRIPTIONS) as Method[]).map((m) => (
          <div key={m}>
            <dt className="font-mono text-sm font-medium text-gray-800 dark:text-gray-200">
              {m}
            </dt>
            <dd className="text-xs text-gray-600 dark:text-gray-400">
              {METHOD_DESCRIPTIONS[m]}
            </dd>
          </div>
        ))}
      </dl>
      <h3 className="mb-2 mt-4 text-sm font-semibold text-gray-900 dark:text-gray-100">
        Add-ons — combine with any method above, per question
      </h3>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {Object.entries(ENHANCER_LABELS).map(([key, label]) => (
          <div key={key}>
            <dt className="text-sm font-medium text-gray-800 dark:text-gray-200">{label}</dt>
            <dd className="text-xs text-gray-600 dark:text-gray-400">
              {ENHANCER_DESCRIPTIONS[key]}
            </dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
        Nothing here needs deciding up front — pick a method and toggle
        add-ons per question when you ask one below, in "Advanced retrieval
        options".
      </p>
    </section>
  );
}

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
  method_details?: {
    retrieval: string;
    degraded?: string[];
    metadata_filter?: { source?: string; document_id?: string };
  } | null;
}

interface Turn {
  question: string;
  response: QueryResponse;
}

/** Shared by the single-shot result panel and each turn in a conversation
 * thread -- `compact` drops the source list for non-latest turns so an
 * ongoing conversation doesn't grow a wall of repeated citations. */
function QueryResultCard({
  response,
  compact = false,
}: {
  response: QueryResponse;
  compact?: boolean;
}) {
  return (
    <>
      <p className="mb-2 whitespace-pre-wrap">{response.answer}</p>
      <p className="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span className={`${badgeClass} ${confidenceBadgeColor(response.confidence)}`}>
          {Math.round(response.confidence * 100)}% confidence
        </span>
        <span>
          Model: {response.model_used}
          {response.tokens_used != null && ` (${response.tokens_used} tokens)`}
        </span>
        <span>
          Method: {response.method}
          {response.method_details?.retrieval && ` (${response.method_details.retrieval} retrieval)`}
        </span>
      </p>
      {response.method_details?.degraded && response.method_details.degraded.length > 0 && (
        <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
          ⚠ Degraded: {response.method_details.degraded.join(", ")}
        </p>
      )}
      {response.method_details?.metadata_filter && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Filtered to: {response.method_details.metadata_filter.source}
        </p>
      )}
      {!compact && response.sources.length > 0 && (
        <div className="mt-3 border-t border-gray-200 pt-2 dark:border-gray-700">
          <p className="mb-1 text-xs font-semibold text-gray-600 dark:text-gray-400">
            Sources
          </p>
          <ul className="flex flex-col gap-1">
            {response.sources.map((s, i) => (
              <li key={i} className="text-xs text-gray-600 dark:text-gray-400">
                [{s.source}] score {s.score.toFixed(3)} — {s.text.slice(0, 200)}
                {s.text.length > 200 && "…"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

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
  const [creating, setCreating] = useState(false);

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
    if (creating) return; // already in flight -- ignore a double-click/tap
    if (!name.trim()) {
      setStatus("Name is required.");
      return;
    }
    if (selected.size === 0) {
      setStatus("Pick at least one knowledge base.");
      return;
    }
    setCreating(true);
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
    } finally {
      setCreating(false);
    }
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">➕</span> Create a pipeline
      </h2>
      {kbs.length === 0 ? (
        <EmptyState>
          Create a knowledge base first — a pipeline needs at least one to
          search over.
        </EmptyState>
      ) : (
        <form onSubmit={handleSubmit}>
          <fieldset disabled={!token || creating} className="mt-2 flex flex-col gap-3">
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
  const sourceFilterId = useId();
  const [question, setQuestion] = useState("");
  const [topK, setTopK] = useState("5");
  const [method, setMethod] = useState<Method>("standard");
  const [rerank, setRerank] = useState(false);
  const [compress, setCompress] = useState(false);
  const [hybrid, setHybrid] = useState(false);
  const [parentContext, setParentContext] = useState(false);
  const [continueConversation, setContinueConversation] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("");
  const [status, setStatus] = useState("");
  const [result, setResult] = useState<QueryResponse | null>(null);
  // Only populated in continue-conversation mode -- server-side context
  // carries across turns via conversation_id regardless, but the UI
  // previously only ever showed the single latest answer, so a user turning
  // this on had no way to see or trust that a conversation thread was
  // actually happening.
  const [turns, setTurns] = useState<Turn[]>([]);

  const methodAvailable = (m: Method) => capabilities?.methods[m] !== false;
  const rerankAvailable = capabilities?.enhancers.rerank.available ?? false;
  const compressAvailable = capabilities?.enhancers.compress.available ?? false;
  const hybridAvailable = capabilities?.retrievers.hybrid.available ?? false;
  const conversationalAvailable = capabilities?.methods.conversational ?? false;
  const advancedActiveCount = [
    rerank,
    compress,
    hybrid,
    parentContext,
    continueConversation,
    sourceFilter.trim().length > 0,
  ].filter(Boolean).length;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) {
      setStatus("Question is required.");
      return;
    }
    let convId = conversationId;
    if (continueConversation && !convId) {
      convId = randomId();
      setConversationId(convId);
    }
    setStatus("Querying…");
    setResult(null);
    try {
      const parsedTopK = parseInt(topK, 10);
      const body: Record<string, unknown> = {
        question,
        // The backend requires top_k >= 1 (models/__init__.py's Field(5, ge=1,
        // le=100)) -- `parseInt(topK, 10) || 5` looked equivalent but treated
        // only 0 as invalid (JS falsy coercion), silently sending negative
        // values straight through to a 422. Explicit bounds check catches both.
        top_k: Number.isNaN(parsedTopK) || parsedTopK < 1 ? 5 : parsedTopK,
        method,
        rerank,
        compress,
        hybrid: parentContext ? false : hybrid,
        parent_context: parentContext,
      };
      if (continueConversation && convId) body.conversation_id = convId;
      if (sourceFilter.trim()) {
        body.metadata_filter = { source: sourceFilter.trim() };
      }
      const res = await apiFetch<QueryResponse>(
        `/v1/rag/pipeline/${pipelineId}/query`,
        { method: "POST", body, token },
      );
      if (continueConversation) {
        setTurns((prev) => [...prev, { question, response: res }]);
        setQuestion(""); // ready for the next follow-up, chat-style
      } else {
        setResult(res);
      }
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
              placeholder="e.g. What does the refund policy say about digital purchases?"
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
                min={1}
                max={100}
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
                <option value="raptor" disabled={!methodAvailable("raptor")}>
                  raptor{!methodAvailable("raptor") && " (unavailable on this host)"}
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
                <p className={fieldHintClass}>{ENHANCER_DESCRIPTIONS.rerank}</p>
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
                <p className={fieldHintClass}>{ENHANCER_DESCRIPTIONS.compress}</p>
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
                <p className={fieldHintClass}>{ENHANCER_DESCRIPTIONS.hybrid}</p>
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
                    ENHANCER_DESCRIPTIONS.parent_context}
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
                      if (!e.target.checked) {
                        setConversationId(null);
                        setTurns([]);
                      }
                    }}
                  />
                  Continue conversation
                  {!conversationalAvailable && " (unavailable on this host)"}
                </label>
                <p className={fieldHintClass}>
                  {ENHANCER_DESCRIPTIONS.continue_conversation} Shows the whole
                  thread below instead of just the latest answer.
                </p>
              </div>
              <div>
                <label className="flex flex-col gap-1 text-sm" htmlFor={sourceFilterId}>
                  Filter by filename
                  <input
                    id={sourceFilterId}
                    className={inputClass}
                    type="text"
                    placeholder="e.g. handbook.pdf"
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value)}
                  />
                </label>
                <p className={fieldHintClass}>
                  Only search chunks from one uploaded file — exact filename
                  match. Leave empty to search everything the pipeline covers.
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
      {continueConversation && turns.length > 0 && (
        <div className="mt-3 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold text-gray-600 dark:text-gray-400">
              Conversation ({turns.length} turn{turns.length === 1 ? "" : "s"})
            </p>
            <button
              type="button"
              onClick={() => {
                setTurns([]);
                setConversationId(null);
              }}
              className="text-xs text-indigo-600 underline hover:text-indigo-700 dark:text-indigo-400"
            >
              Reset conversation
            </button>
          </div>
          {turns.map((turn, i) => (
            <div key={i} className="rounded-lg bg-gray-50 p-4 text-sm dark:bg-gray-800">
              <p className="mb-2 text-xs font-semibold text-gray-500 dark:text-gray-400">
                Q: {turn.question}
              </p>
              <QueryResultCard response={turn.response} compact={i < turns.length - 1} />
            </div>
          ))}
        </div>
      )}
      {!continueConversation && result && (
        <div className="mt-3 rounded-lg bg-gray-50 p-4 text-sm dark:bg-gray-800">
          <QueryResultCard response={result} />
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
  onUpdated,
  confirm,
}: {
  pipeline: RagPipeline;
  token: string;
  capabilities: Capabilities | null;
  onDeleted: (id: string) => void;
  onUpdated: (pipeline: RagPipeline) => void;
  confirm: ReturnType<typeof useConfirm>["confirm"];
}) {
  const [status, setStatus] = useState("");
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState(pipeline.name);
  const [saving, setSaving] = useState(false);

  async function handleRename() {
    if (!editName.trim()) {
      setStatus("Name can't be empty.");
      return;
    }
    setSaving(true);
    setStatus("Saving…");
    try {
      const updated = await apiFetch<RagPipeline>(
        `/v1/rag/pipeline/${pipeline.id}`,
        { method: "PATCH", body: { name: editName.trim() }, token },
      );
      onUpdated(updated);
      setStatus("");
      setEditing(false);
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setSaving(false);
  }

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
    if (!(await copyText(pipeline.id))) return;
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <section className={`mb-4 ${cardClass}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {editing ? (
            <div className="flex items-center gap-2">
              <input
                className={inputClass}
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                aria-label="Pipeline name"
                disabled={saving}
              />
              <button
                className={primaryButtonClass}
                onClick={handleRename}
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
          ) : (
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
              <span aria-hidden="true">🧠</span> {pipeline.name}
            </h2>
          )}
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
        {!editing && (
          <div className="flex shrink-0 gap-2">
            <button
              className={secondaryButtonClass}
              onClick={() => {
                setEditName(pipeline.name);
                setStatus("");
                setEditing(true);
              }}
              disabled={!token}
            >
              ✏️ Rename
            </button>
            <button
              className={destructiveButtonClass}
              onClick={handleDelete}
              disabled={!token}
            >
              🗑 Delete
            </button>
          </div>
        )}
      </div>
      {!token && (
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
          Log in to rename or delete this pipeline.
        </p>
      )}
      <StatusLine isError={false}>{status}</StatusLine>
      <QueryPanel
        pipelineId={pipeline.id}
        token={token}
        capabilities={capabilities}
        onGone={() => onDeleted(pipeline.id)}
      />
    </section>
  );
}

/** Auto-router (method="auto") analytics, from GET /v1/rag/decision-stats. The
 * decision engine records the strategy/complexity/confidence of every auto query;
 * this surfaces the cumulative distribution so you can see how it's behaving.
 * Rendered only when the engine is available (Ollama up) — hidden otherwise so it
 * doesn't add noise on deployments that don't use the auto method. */
export function AutoRouterStatsCard({ stats }: { stats: DecisionStats | null }) {
  if (!stats || !stats.available) return null;

  const dist = (counts: Record<string, number>) =>
    Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .map(([k, n]) => (
        <span key={k} className={badgeClass}>
          {k}: {n}
        </span>
      ));

  return (
    <div className={`${cardClass} mb-4`}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
          🧭 Auto-router analytics
        </h3>
        <span className={mutedTextClass}>
          {stats.total_decisions} decision
          {stats.total_decisions === 1 ? "" : "s"} recorded
        </span>
      </div>
      {stats.total_decisions === 0 ? (
        <p className={mutedTextClass}>
          No <code>method=auto</code> queries recorded yet — run one to see which
          retrieval strategy the router picks. Counts are in-memory and reset on
          restart.
        </p>
      ) : (
        <div className="flex flex-col gap-2 text-xs">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-gray-600 dark:text-gray-400">
              Strategy:
            </span>
            {dist(stats.strategy_distribution)}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-medium text-gray-600 dark:text-gray-400">
              Complexity:
            </span>
            {dist(stats.complexity_distribution)}
          </div>
          {stats.avg_confidence !== null && (
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-gray-600 dark:text-gray-400">
                Avg confidence:
              </span>
              <span
                className={`inline-block rounded-full px-2 py-0.5 font-medium ${confidenceBadgeColor(
                  stats.avg_confidence,
                )}`}
              >
                {(stats.avg_confidence * 100).toFixed(0)}%
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function RagPipelinesPage() {
  const { token } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [decisionStats, setDecisionStats] = useState<DecisionStats | null>(null);
  const [pipelines, setPipelines] = useState<RagPipeline[]>([]);
  const [filter, setFilter] = useState("");
  const [status, setStatus] = useState("");
  const [isError, setIsError] = useState(false);

  const visiblePipelines = filterByText(pipelines, filter, (p) => [
    p.name,
    ...p.knowledge_base_ids,
  ]);

  const setStatusMsg = useCallback((msg: string, err = false) => {
    setStatus(msg);
    setIsError(err);
  }, []);

  const load = useCallback(async () => {
    setStatusMsg("Loading…");
    try {
      const [kbList, caps, pipelineList, stats] = await Promise.all([
        apiFetch<Paginated<KnowledgeBase>>("/v1/rag/knowledge-bases?limit=100"),
        apiFetch<Capabilities>("/v1/rag/capabilities"),
        apiFetch<Paginated<RagPipeline>>("/v1/rag/pipeline?limit=100"),
        // Newer endpoint (auto-router analytics) — degrade gracefully rather than
        // failing the whole page load against a backend that predates it.
        apiFetch<DecisionStats>("/v1/rag/decision-stats").catch(() => null),
      ]);
      setKbs(kbList.items);
      setCapabilities(caps);
      setPipelines(pipelineList.items);
      setDecisionStats(stats);
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

  function handlePipelineUpdated(updated: RagPipeline) {
    setPipelines((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
  }

  return (
    <>
      {dialog}
      <PageHeader icon="🔎" title="RAG Pipelines" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Combine one or more knowledge bases into a queryable pipeline, then
        ask it questions using Minder's own retrieval methods — this is
        separate from OpenWebUI's own disconnected Knowledge feature.
      </p>
      <RetrievalMethodsReference />
      <AutoRouterStatsCard stats={decisionStats} />
      <StatusLine isError={isError}>{status}</StatusLine>
      <CreatePipelineForm
        token={token}
        kbs={kbs}
        onCreated={(p) => setPipelines((prev) => [...prev, p])}
      />
      {pipelines.length === 0 && (
        <EmptyState>
          No pipelines created yet — pick at least one knowledge base above.
        </EmptyState>
      )}
      {pipelines.length > 1 && (
        <div className="mb-3 flex items-center gap-3">
          <input
            className={`${inputClass} max-w-xs`}
            type="text"
            placeholder="Filter by name or knowledge base id…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter pipelines"
          />
          {filter.trim() && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {visiblePipelines.length} of {pipelines.length}
            </span>
          )}
        </div>
      )}
      {pipelines.length > 0 && visiblePipelines.length === 0 && (
        <EmptyState>No pipelines match "{filter}".</EmptyState>
      )}
      {visiblePipelines.map((p) => (
        <PipelineCard
          key={p.id}
          pipeline={p}
          token={token}
          capabilities={capabilities}
          onDeleted={handlePipelineDeleted}
          onUpdated={handlePipelineUpdated}
          confirm={confirm}
        />
      ))}
    </>
  );
}
