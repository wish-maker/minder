import { useId, useState } from "react";

import { useConfirm } from "../components/ConfirmDialog";
import { InfoCallout } from "../components/InfoCallout";
import { PageHeader } from "../components/PageHeader";
import { StatusLine } from "../components/StatusLine";
import { apiFetch, friendlyErrorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  cardClass,
  destructiveButtonClass,
  inputClass,
  primaryButtonClass,
  secondaryButtonClass,
} from "../lib/ui";

interface Entity {
  text: string;
  label: string;
  [key: string]: unknown;
}

interface Relationship {
  source: string;
  target: string;
  type: string;
  [key: string]: unknown;
}

interface ExtractResponse {
  success: boolean;
  entities: Entity[];
  relationships: Relationship[];
  entity_count: number;
  relationship_count: number;
}

interface ConstructResponse {
  success: boolean;
  document_id: string;
  entity_count: number;
  relationship_count: number;
  message: string;
}

interface RelatedEntity {
  text: string;
  [key: string]: unknown;
}

interface RetrieveResponse {
  success: boolean;
  query: string;
  related_entities: RelatedEntity[];
  entity_count: number;
  retrieval_time_ms: number;
}

interface EntityContextResponse {
  success: boolean;
  entity: Record<string, unknown>;
  related_entities: RelatedEntity[];
  documents: { id?: string; title?: string }[];
  context_window: number;
}

function EntityBadge({ entity }: { entity: Entity | RelatedEntity }) {
  const label = "label" in entity ? String(entity.label) : undefined;
  return (
    <span className="inline-block rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300">
      {entity.text}
      {label && <span className="ml-1 opacity-70">({label})</span>}
    </span>
  );
}

interface BuiltDoc {
  documentId: string;
  title: string;
  entityCount: number;
  relationshipCount: number;
}

function ExtractAndBuildCard({
  token,
  onBuilt,
}: {
  token: string;
  onBuilt: (doc: BuiltDoc) => void;
}) {
  const titleId = useId();
  const textId = useId();
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState<ExtractResponse | null>(null);
  const [built, setBuilt] = useState<ConstructResponse | null>(null);

  async function handlePreview() {
    if (!text.trim()) {
      setStatus("Text is required.");
      return;
    }
    setBusy(true);
    setStatus("Extracting…");
    setPreview(null);
    setBuilt(null);
    try {
      const res = await apiFetch<ExtractResponse>("/v1/graph-rag/extract", {
        method: "POST",
        body: { text, extract_relationships: true },
        token,
      });
      setPreview(res);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  async function handleBuild() {
    if (!text.trim()) {
      setStatus("Text is required.");
      return;
    }
    setBusy(true);
    setStatus("Building knowledge graph…");
    setBuilt(null);
    try {
      const documentId = crypto.randomUUID();
      const res = await apiFetch<ConstructResponse>("/v1/graph-rag/construct-graph", {
        method: "POST",
        body: {
          document_id: documentId,
          text,
          title: title || "Untitled",
          source: "client-graph-explorer",
          extract_relationships: true,
        },
        token,
      });
      setBuilt(res);
      onBuilt({
        documentId: res.document_id,
        title: title || "Untitled",
        entityCount: res.entity_count,
        relationshipCount: res.relationship_count,
      });
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🧬</span> Extract &amp; Build
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Paste text to see what entities and relationships spaCy finds in it —
        preview first (nothing saved), or build it straight into the Neo4j
        knowledge graph.
      </p>
      <fieldset disabled={!token} className="flex flex-col gap-3">
        <div>
          <label
            htmlFor={titleId}
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Title (optional, only used when building)
          </label>
          <input
            id={titleId}
            className={inputClass}
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Q3 board meeting notes"
          />
        </div>
        <div>
          <label
            htmlFor={textId}
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Text
          </label>
          <textarea
            id={textId}
            className={inputClass}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste a paragraph or two mentioning people, places, organizations…"
          />
        </div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={handlePreview} disabled={busy} className={secondaryButtonClass}>
            Preview extraction
          </button>
          <button type="button" onClick={handleBuild} disabled={busy} className={primaryButtonClass}>
            Build knowledge graph
          </button>
          <span className="text-sm text-gray-500 dark:text-gray-400">{status}</span>
        </div>
      </fieldset>

      {preview && (
        <div className="mt-3 rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
            {preview.entity_count} entities, {preview.relationship_count} relationships found
            — nothing saved yet.
          </p>
          {preview.entities.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              No entities found — try a longer passage with named people, places, or organizations.
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {preview.entities.map((e, i) => (
                <EntityBadge key={i} entity={e} />
              ))}
            </div>
          )}
          {preview.relationships.length > 0 && (
            <ul className="mt-2 flex flex-col gap-0.5 text-xs text-gray-600 dark:text-gray-400">
              {preview.relationships.map((r, i) => (
                <li key={i}>
                  {r.source} —[{r.type}]→ {r.target}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {built && (
        <div className="mt-3 rounded-lg border border-green-200 bg-green-50 p-3 text-sm text-green-900 dark:border-green-800 dark:bg-green-950 dark:text-green-100">
          ✅ {built.message} — {built.entity_count} entities, {built.relationship_count}{" "}
          relationships written. Document id: <code>{built.document_id}</code>
        </div>
      )}
    </section>
  );
}

function ExploreCard({ token }: { token: string }) {
  const [mode, setMode] = useState<"search" | "entity">("search");
  const [query, setQuery] = useState("");
  const [entityText, setEntityText] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [retrieveResult, setRetrieveResult] = useState<RetrieveResponse | null>(null);
  const [contextResult, setContextResult] = useState<EntityContextResponse | null>(null);

  async function handleSearch() {
    if (!query.trim()) {
      setStatus("Query is required.");
      return;
    }
    setBusy(true);
    setStatus("Searching…");
    setRetrieveResult(null);
    try {
      const res = await apiFetch<RetrieveResponse>("/v1/graph-rag/retrieve", {
        method: "POST",
        body: { query, limit: 10, traversal_depth: 2 },
        token,
      });
      setRetrieveResult(res);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  async function handleEntityLookup() {
    if (!entityText.trim()) {
      setStatus("Entity name is required.");
      return;
    }
    setBusy(true);
    setStatus("Looking up…");
    setContextResult(null);
    try {
      const res = await apiFetch<EntityContextResponse>("/v1/graph-rag/entity-context", {
        method: "POST",
        body: { entity_text: entityText, include_neighbors: true, context_window: 5 },
        token,
      });
      setContextResult(res);
      setStatus("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🔍</span> Explore
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Search the graph by meaning, or look up a specific entity's neighbors
        and source documents — this is a different retrieval path from RAG
        Pipelines' vector search, over the same underlying knowledge.
      </p>
      <div className="mb-3 flex gap-2 border-b border-gray-100 dark:border-gray-800">
        <button
          type="button"
          onClick={() => setMode("search")}
          className={`border-b-2 pb-1.5 text-sm font-medium ${
            mode === "search"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-gray-500 dark:text-gray-400"
          }`}
        >
          Search
        </button>
        <button
          type="button"
          onClick={() => setMode("entity")}
          className={`border-b-2 pb-1.5 text-sm font-medium ${
            mode === "entity"
              ? "border-indigo-600 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-gray-500 dark:text-gray-400"
          }`}
        >
          Entity lookup
        </button>
      </div>

      <fieldset disabled={!token}>
        {mode === "search" ? (
          <div className="flex gap-2">
            <input
              className={inputClass}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="What are you looking for?"
              aria-label="Search the knowledge graph"
            />
            <button type="button" onClick={handleSearch} disabled={busy} className={primaryButtonClass}>
              Search
            </button>
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              className={inputClass}
              value={entityText}
              onChange={(e) => setEntityText(e.target.value)}
              placeholder="e.g. a person or company name"
              aria-label="Entity name to look up"
            />
            <button type="button" onClick={handleEntityLookup} disabled={busy} className={primaryButtonClass}>
              Look up
            </button>
          </div>
        )}
      </fieldset>
      <StatusLine>{status}</StatusLine>

      {mode === "search" && retrieveResult && (
        <div className="rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
            {retrieveResult.entity_count} related entities · {Math.round(retrieveResult.retrieval_time_ms)}ms
          </p>
          {retrieveResult.related_entities.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Nothing found — the graph may not have any documents built yet (see Extract &amp; Build above).
            </p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {retrieveResult.related_entities.map((e, i) => (
                <EntityBadge key={i} entity={e} />
              ))}
            </div>
          )}
        </div>
      )}

      {mode === "entity" && contextResult && (
        <div className="rounded-lg bg-gray-50 p-3 text-sm dark:bg-gray-800">
          {Object.keys(contextResult.entity).length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Entity not found in the graph.
            </p>
          ) : (
            <>
              <p className="mb-1 font-medium text-gray-900 dark:text-gray-100">
                {entityText}
              </p>
              {contextResult.related_entities.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {contextResult.related_entities.map((e, i) => (
                    <EntityBadge key={i} entity={e} />
                  ))}
                </div>
              )}
              {contextResult.documents.length > 0 && (
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Mentioned in: {contextResult.documents.map((d) => d.title || d.id).join(", ")}
                </p>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

function DeleteDocumentCard({
  token,
  confirm,
  builtDocs,
  onDeleted,
}: {
  token: string;
  confirm: ReturnType<typeof useConfirm>["confirm"];
  builtDocs: BuiltDoc[];
  onDeleted: (documentId: string) => void;
}) {
  const [documentId, setDocumentId] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    if (!documentId.trim()) {
      setStatus("Document id is required.");
      return;
    }
    const ok = await confirm({
      title: "Remove document from graph?",
      message: `This permanently removes document "${documentId}"'s relationships and any entities that only it referenced from Neo4j. Entities shared with other documents are kept.`,
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    setStatus("Deleting…");
    try {
      await apiFetch(`/v1/graph-rag/graph/document/${encodeURIComponent(documentId)}`, {
        method: "DELETE",
        token,
      });
      setStatus("Deleted (idempotent — reports success even if the id was already gone).");
      onDeleted(documentId);
      setDocumentId("");
    } catch (e) {
      setStatus(friendlyErrorMessage(e));
    }
    setBusy(false);
  }

  return (
    <section className={`mb-6 ${cardClass}`}>
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-gray-100">
        <span aria-hidden="true">🗑</span> Remove a document's graph
      </h2>
      <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
        Removes one document's relationships and orphaned entities from
        Neo4j (entities shared with other documents are kept). There's no
        full document browser here yet — pick one you built this session
        below, or paste any other document id.
      </p>
      {builtDocs.length > 0 && (
        <div className="mb-3 flex flex-col gap-1">
          <p className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Built this session:
          </p>
          <ul className="flex flex-col gap-1">
            {builtDocs.map((doc) => (
              <li key={doc.documentId}>
                <button
                  type="button"
                  onClick={() => setDocumentId(doc.documentId)}
                  className="text-left text-xs text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  {doc.title} — {doc.entityCount} entities, {doc.relationshipCount} relationships{" "}
                  <code className="text-gray-500 dark:text-gray-400">({doc.documentId})</code>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      <fieldset disabled={!token} className="flex items-center gap-2">
        <input
          className={inputClass}
          aria-label="Document id"
          value={documentId}
          onChange={(e) => setDocumentId(e.target.value)}
          placeholder="document id"
        />
        <button type="button" onClick={handleDelete} disabled={busy} className={destructiveButtonClass}>
          Delete
        </button>
      </fieldset>
      <StatusLine>{status}</StatusLine>
    </section>
  );
}

export function GraphExplorerPage() {
  const { token } = useAuth();
  const { confirm, dialog } = useConfirm();
  const [builtDocs, setBuiltDocs] = useState<BuiltDoc[]>([]);

  function handleBuilt(doc: BuiltDoc) {
    setBuiltDocs((prev) => [doc, ...prev.filter((d) => d.documentId !== doc.documentId)]);
  }

  function handleDeleted(documentId: string) {
    setBuiltDocs((prev) => prev.filter((d) => d.documentId !== documentId));
  }

  return (
    <>
      <PageHeader icon="🧬" title="Knowledge Graph" />
      <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">
        Build and explore a knowledge graph from your text — spaCy extracts
        entities and relationships, Neo4j stores them. A different retrieval
        paradigm from vector-search RAG Pipelines: this finds{" "}
        <em>who's connected to whom</em>, not just similar-sounding chunks.
      </p>
      <InfoCallout icon="ℹ️">
        This graph is separate from the plugin dependency graph shown on the
        Marketplace page — same underlying Neo4j instance, unrelated data.
      </InfoCallout>
      {dialog}
      <ExtractAndBuildCard token={token} onBuilt={handleBuilt} />
      <ExploreCard token={token} />
      <DeleteDocumentCard
        token={token}
        confirm={confirm}
        builtDocs={builtDocs}
        onDeleted={handleDeleted}
      />
    </>
  );
}
