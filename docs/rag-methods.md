# RAG Methods in Minder

**Status as of 2026-07-24** (verified against the running `minder-rag-pipeline` +
`GET /capabilities`; supersedes the earlier 2026-07-10 "research lab" framing).

## Executive Summary

Minder splits retrieval-augmented generation across two services:

- **`minder-rag-pipeline` (`:8004`)** — text RAG. The live query endpoint
  (`POST /pipeline/{id}/query`) supports **Standard (dense) RAG**, **Conversational
  RAG** (via `conversation_id`), and the advanced methods **HyDE**, **Self-RAG**,
  **auto** (decision engine), and **Corrective RAG** — all selected via the request
  `method` field. Two orthogonal enhancers apply to any method: **re-ranking**
  (`rerank`, cross-encoder when `sentence-transformers` is present, else an LLM
  re-rank) and **contextual compression** (`compress`). Two retrieval strategies are
  also selectable: **hybrid** dense+BM25 (`hybrid`) and **parent-child / small-to-big**
  (`parent_context`). `GET /capabilities` reports exactly what is live on the host.
- **`minder-graph-rag` (`:8008`)** — graph RAG. spaCy NER entity extraction +
  Neo4j knowledge-graph construction and retrieval.

These methods **self-degrade by hardware**: e.g. the re-ranker uses a cross-encoder
only when `sentence-transformers`/torch is installed (otherwise a lightweight LLM
re-rank), and hybrid needs `rank-bm25`. `GET /capabilities` makes that choice
transparent. Every technique in Bucket 1 is reachable through the live endpoint;
**RAPTOR** is the one commonly-cited technique that is **not implemented** here (a
candidate — see Bucket 2).

> How methods/enhancers are requested (all on `POST /pipeline/{id}/query`):
> `{"question": "...", "top_k": 5, "method": "standard|hyde|self_rag|auto|corrective",
> "conversation_id": "...", "rerank": false, "compress": false, "hybrid": false,
> "parent_context": false}`.

---

## Bucket 1: Supported (wired into the live query flow)

### Standard RAG (Dense Vector Retrieval)

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **LIVE** — default method in `minder-rag-pipeline:8004` |
| **Implementation** | `routes/rag.py` (`retrieve_relevant_documents`) + `rag/runner.py` |
| **Pipeline** | 1. Chunk: `RecursiveCharacterTextSplitter` (langchain)<br>2. Embed: Ollama `nomic-embed-text` (768-dim, cosine)<br>3. Store: Qdrant dense vectors<br>4. Retrieve: Qdrant similarity search (top-k)<br>5. Generate: Llama3.2 via Ollama with context prompt |
| **API** | `POST /knowledge-base` · `POST /knowledge-base/{id}/upload` · `POST /pipeline` · `POST /pipeline/{id}/query` |

### Conversational RAG (multi-turn)

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **LIVE** — set `conversation_id` on the query |
| **Implementation** | `rag/runner.py` + `repositories/conversation_repository.py` (PostgreSQL `conversation_turns`) |
| **Pipeline** | Fetch last `max_turns=3` turns → prepend as context → generate → store the new turn |
| **Known limits** | `user_id="default"` (single-user); long conversations can pressure the context window |

### HyDE · Self-RAG · auto (decision engine) · Corrective RAG

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **LIVE** — `method: "hyde" \| "self_rag" \| "auto" \| "corrective"` |
| **Implementation** | `rag/methods/` (hyde, self_rag, decision, corrective) + `domain/` (expansion, pipelines) + `agent/decision_engine.py`, orchestrated by `rag/runner.py` |
| **HyDE** | Retrieve using an LLM-generated hypothetical answer instead of the raw question |
| **Self-RAG** | Self-critique / quality-graded generation loop |
| **auto** | The decision engine picks HyDE/Self-RAG per query |
| **Corrective (CRAG)** | Grades retrieval; re-retrieves with a refined query when weak (web-search fallback is optional, gated on TAVILY/SERPER keys) |
| **Verify** | `GET /capabilities` → `methods` |

### Graph RAG

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **LIVE** — `minder-graph-rag:8008` |
| **Implementation** | `src/services/graph-rag/` (spaCy NER + Neo4j) |
| **API** | `POST /extract` · `POST /construct-graph` · `POST /retrieve` · `POST /entity-context` |

### Enhancers (orthogonal, apply to any method)

| Enhancer | Flag | Status |
|----------|------|--------|
| **Re-ranking** | `rerank: true` | ✅ **LIVE** — cross-encoder (`domain/rerankers/cross_encoder.py`) when `sentence-transformers` present, else LLM re-rank. Backend reported by `/capabilities`. |
| **Contextual compression** | `compress: true` | ✅ **LIVE** — `domain/compressors/contextual.py` extracts query-relevant sentences before generation |

### Retrieval strategies (#45)

| Strategy | Flag | Status |
|----------|------|--------|
| **Hybrid (dense + BM25)** | `hybrid: true` | ✅ **LIVE** — `domain/retrievers/hybrid.py`; needs `rank-bm25`. BM25 index built lazily from the stored Qdrant chunks (rebuilt on demand, invalidated on upload). |
| **Parent-child (small-to-big)** | `parent_context: true` | ✅ **LIVE** — `retrieve_parent_child` in `routes/rag.py`: match precise child chunks, return each with its neighbour window (adjacent `chunk_index`). Reuses stored `chunk_index` — no ingest-model change. |

Precedence when multiple retrieval flags are set: `parent_context` > `hybrid` > dense.

---

## Bucket 2: Candidate techniques (not implemented)

None of these ship today — there is **no `raptor_rag.py`** (or equivalent) anywhere in
the tree. They are all buildable on the current architecture:

| Method | What would be needed | Feasibility |
|--------|----------------------|-------------|
| **RAPTOR** | Hierarchical chunk clustering → LLM tree summaries → level-aware retrieval; needs tree construction on upload, tree storage, and a retrieve variant | MEDIUM |
| **Multi-Query RAG** | LLM query expansion (Ollama) + fusion | MEDIUM |
| **Decomposition RAG** | Query decomposition + sub-question routing | MEDIUM |
| **Metadata Filtering** | Qdrant supports it — expose filter params on the query endpoint | HIGH |

---

## Bucket 3: Out of scope / major rework

| Method | Why out of scope |
|--------|------------------|
| **Agentic RAG** | Needs a full agent framework (tool calling, decision loops) |
| **Streaming RAG** | Needs SSE/WebSocket streaming infra — current flow is batch |
| **Federated RAG** | Multi-node/federation — single-node Pi deployment |
| **Long-Context RAG** | Needs a long-context model — Llama3.2 context is limited |

---

## Summary

| Bucket | Count | Methods |
|--------|-------|---------|
| **Live (wired)** | 8 methods + 2 enhancers + 2 retrievers | Standard, Conversational, HyDE, Self-RAG, auto, Corrective, Graph RAG (+ rerank, compress; + hybrid, parent-child) |
| **Buildable (not implemented)** | 4 | RAPTOR, Multi-Query, Decomposition, Metadata Filtering |
| **Out of scope** | 4 | Agentic, Streaming, Federated, Long-Context |

> **Takeaway**: `minder-rag-pipeline` now serves a full method set (Standard +
> Conversational + HyDE/Self-RAG/auto/Corrective, with optional rerank/compress and
> hybrid/parent-child retrieval), and `minder-graph-rag` serves spaCy-NER + Neo4j
> graph RAG. `GET /capabilities` is the source of truth for what's active on a given
> host. RAPTOR is **not** implemented — it is a candidate technique (Bucket 2).

---

**Last Updated:** 2026-07-24
