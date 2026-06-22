# RAG Methods in Minder

**Status as of 2026-06-22**

## Executive Summary

This project has **2 production RAG methods proven working**:
- **Standard RAG** — chunking, embedding (Ollama nomic-embed-text), Qdrant dense retrieval, Llama3.2 generation
- **Graph RAG** — spaCy entity extraction, Neo4j graph storage, graph-based retrieval

Additionally, this codebase contains **8 advanced RAG methods implemented as standalone modules** — a "RAG research lab" — usable as a foundation but **NOT currently wired into the active pipeline** and **mostly untested**.

> **⚠️ Important:** The active `minder-rag-pipeline` service (`:8004`, `src/services/rag-pipeline/main.py`) only implements Standard RAG. All other methods are separate modules that would need integration work to become functional in a production query flow.

---

## Bucket 1: Supported (Production-Ready)

These methods are **implemented, wired, and proven via manual end-to-end test** in the active service.

### Standard RAG (Dense Vector Retrieval)

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **PRODUCTION READY** — Active in `minder-rag-pipeline:8004` |
| **Implementation** | `src/services/rag-pipeline/main.py` (lines 260-636) |
| **Test Status** | ✅ Proven via manual test: `kb create` → `upload` → `query` → answer returned |
| **Pipeline** | 1. Chunk: `RecursiveCharacterTextSplitter` (langchain)<br>2. Embed: Ollama `nomic-embed-text` (768-dim, cosine)<br>3. Store: Qdrant dense vectors<br>4. Retrieve: Qdrant similarity search (top-k)<br>5. Generate: Llama3.2 via Ollama with context prompt |
| **API Endpoints** | `POST /knowledge-base` — Create KB<br>`POST /knowledge-base/{id}/upload` — Ingest document<br>`POST /pipeline/{id}/query` — Query RAG pipeline |
| **Config** | Chunk size (default 512), overlap (50), embedding model, LLM model |

### Graph RAG

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **PRODUCTION READY** — Active in `minder-graph-rag:8008` |
| **Implementation** | `src/services/graph-rag/main.py` + `core/` modules |
| **Test Status** | ✅ Proven via manual test: 18 sentences → 141 entities/relationships extracted, 7 retrieved |
| **Pipeline** | 1. Extract: spaCy `en_core_web_sm` entity/relationship extraction<br>2. Store: Neo4j graph (`Entity` nodes, `RELATES_TO` edges)<br>3. Retrieve: Graph traversal, entity context, related entities |
| **API Endpoints** | `POST /extract` — Extract entities from text<br>`POST /construct-graph` — Build knowledge graph<br>`POST /retrieve` — Graph-based retrieval<br>`POST /entity-context` — Get entity context |
| **Config** | Neo4j URI, auth credentials, spaCy model |

### Conversational RAG (Multi-turn with Context)

| Attribute | Value |
|-----------|-------|
| **Status** | ✅ **PRODUCTION READY** — Active in `minder-rag-pipeline:8004` |
| **Implementation** | `src/services/rag-pipeline/main.py` (query endpoint) + `repositories/conversation_repository.py` |
| **Test Status** | ✅ Proven via 3-turn test + clean install: Turn 1 → Turn 2 (pronoun "it") → Turn 3 (pronoun "that") → 3 rows verified in `conversation_turns` table |
| **Pipeline** | 1. Query with optional `conversation_id`<br>2. Fetch last 3 turns from PostgreSQL (per conversation)<br>3. Build context: "Previous conversation: Q1/A1\nQ2/A2\nQ3/A3"<br>4. Combine with RAG context → LLM prompt<br>5. Store new Q&A turn after response |
| **API Endpoints** | `POST /pipeline/{id}/query` — Set `conversation_id` to enable conversation history |
| **Config** | `max_turns=3` (conversation context limit), uses same embedding/LLM models as Standard RAG |
| **Database Schema** | `conversation_turns` table: `id, user_id, conversation_id, question, answer, timestamp, metadata` with index on `(user_id, conversation_id, timestamp DESC)` |
| **Known Limitations** | • `user_id="default"` hardcode — single-user only; future multi-user would need real user_id<br>• Token budget — `max_turns=3` helps but long conversations could overflow Llama3.2 context window |

---

## Bucket 2: Partial / Infrastructure Available

These methods are **implemented as standalone modules** but **NOT wired into the active pipeline**. Most have minimal or no functional tests.

### RAPTOR (Recursive Abstractive Processing for Tree-Organized Retrieval)

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** — 1092 lines of code, not integrated |
| **Implementation** | `src/services/rag-pipeline/raptor_rag.py` |
| **Test Status** | ✅ **HAS TESTS** — `test_raptor.py` (416 lines): unit tests for chunker/retriever, integration tests, edge cases (empty text, non-ASCII). Has `if __name__ == "__main__"` block. |
| **Dependencies** | None (uses numpy optionally, has pure-Python fallback) |
| **What it does** | Hierarchical clustering of chunks → LLM summaries → tree structure → level-aware retrieval based on query specificity |
| **What's missing** | Wiring into main pipeline (no API endpoint, no integration with Qdrant/Ollama) |
| **To activate** | 1. Add RAPTOR option to KB creation<br>2. Call `RAPTORChunker.create_tree_structure()` on upload<br>3. Use `RAPTORRetriever.retrieve_from_tree()` in query flow<br>4. Store tree structure in PostgreSQL |
| **Line count** | 1092 (largest single module in codebase) |

### HyDE (Hypothetical Document Embeddings)

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/expansion/hyde.py` (183 lines) |
| **Test Status** | ⚠️ **IMPORT TEST ONLY** — `test_architecture.py` line 29 checks import succeeds, no functional test |
| **Dependencies** | Ollama LLM (for hypothetical answer generation) |
| **What it does** | Generates hypothetical answer to query → embeds hypothetical text → uses hypothetical embedding for search (improves precision over raw query) |
| **What's missing** | 1. Wiring into query flow<br>2. Test coverage (never verified correct hypothetical generation) |
| **To activate** | Add HyDE step before retrieval in `RetrievalService.retrieve()` |

### Hybrid Search (Dense + Sparse BM25)

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/retrievers/hybrid.py` (262 lines) |
| **Test Status** | ⚠️ **BASIC TEST** — `test_architecture.py` lines 125-127 test initialization only |
| **Dependencies** | `rank-bm25` (optional, runtime check) |
| **What it does** | Combines dense vector search (Qdrant) + BM25 sparse keyword search with weighted `alpha` parameter |
| **What's missing** | 1. BM25 index building on document upload<br>2. Wiring into query flow<br>3. Functional test of hybrid search results |
| **To activate** | 1. Build BM25 index when documents uploaded<br>2. Add hybrid search step in retrieval, combine scores<br>3. Expose `alpha` parameter in API |

### Cross-Encoder Re-ranking

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/rerankers/cross_encoder.py` (144 lines) |
| **Test Status** | ⚠️ **BASIC TEST** — `test_architecture.py` lines 139-143 test structure only |
| **Dependencies** | `sentence_transformers` (optional, lazy-loaded, disabled by default) |
| **What it does** | Re-ranks retrieved documents using cross-encoder model for better precision |
| **What's missing** | 1. Wiring into query flow (post-retrieval step)<br>2. Model download/storage strategy<br>3. Test with actual model |
| **To activate** | Add re-ranking step after dense retrieval, before context building |
| **Note** | Uses `cross-encoder/ms-marco-MiniLM-L-6-v2`, CPU-only for RPi 4 |

### Self-RAG (Quality-Based Iterative Refinement)

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/pipelines/self_rag.py` (206 lines) |
| **Test Status** | ⚠️ **IMPORT TEST ONLY** — `test_architecture.py` line 28, no functional test |
| **Dependencies** | `quality_evaluator.py` (requires `sentence_transformers`) |
| **What it does** | Generate → Evaluate quality → Refine if below threshold → Repeat |
| **What's missing** | 1. Quality evaluator wiring<br>2. Test of refinement loop<br>3. Integration with main pipeline |
| **To activate** | Wrap generation step with Self-RAG loop in query flow |

### Contextual Compression

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/compressors/contextual.py` (200 lines) |
| **Test Status** | ⚠️ **BASIC TEST** — `test_architecture.py` lines 130-136 test structure only |
| **Dependencies** | None (pure Python, sentence splitting) |
| **What it does** | Compresses retrieved context by extracting query-relevant sentences (word overlap scoring) |
| **What's missing** | 1. Wiring into query flow (post-retrieval)<br>2. Test of compression quality |
| **To activate** | Add compression step after retrieval, before generation |

### Parent-Child Retriever

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/domain/retrievers/parent_child.py` (181 lines) |
| **Test Status** | ⚠️ **IMPORT TEST ONLY** — `test_architecture.py` line 25, no functional test |
| **Dependencies** | None |
| **What it does** | Small child chunks for precise search, returns parent chunks for better context |
| **What's missing** | 1. Parent-child hierarchy building on upload<br>2. Wiring into query flow |
| **To activate** | 1. Build parent-child hierarchy during chunking<br>2. Use in retrieval to return parent context |

### Corrective RAG (CRAG)

| Attribute | Value |
|-----------|-------|
| **Status** | 🔶 **UNWIRED MODULE** |
| **Implementation** | `src/services/rag-pipeline/corrective_rag.py` (309 lines) |
| **Test Status** | ❌ **NO TESTS** — No test file, no evidence of execution |
| **Dependencies** | `httpx`, TAVILY_API_KEY or SERPER_API_KEY (both optional) |
| **What it does** | Evaluates retrieval quality → Falls back to web search (Tavily/Serper) if quality poor |
| **What's missing** | 1. Wiring into query flow<br>2. Test coverage<br>3. Web search API configuration |
| **To activate** | Add quality evaluation step after retrieval, conditional web search fallback |

---

## Bucket 3: Buildable on Current Architecture

These methods are **not implemented** but could be built using existing infrastructure.

| Method | What Would Be Needed | Feasibility |
|--------|----------------------|--------------|
| **Multi-Query RAG** | LLM query expansion (Ollama) + multi-query fusion | **MEDIUM** — Use Llama3.2 to generate query variants |
| **Decomposition RAG** | Query decomposition logic + sub-question routing | **MEDIUM** — Similar to Multi-Query, more complex orchestration |
| **Metadata Filtering** | Qdrant supports it, just need API exposure | **HIGH** — Add filter params to query endpoint |
| **Modular RAG** | Architecture exists (`api_v2.py` clean architecture) — just needs wiring | **MEDIUM** — Connect optional components in `RetrievalService` |

---

## Bucket 4: Out of Scope / Major Rework Needed

These would require **fundamentally different architecture** or are outside project scope.

| Method | Why Out of Scope |
|--------|------------------|
| **Agentic RAG** | Would require full agent framework with tool calling, decision loops — completely different paradigm |
| **Streaming RAG** | Would require streaming response infrastructure (SSE/WebSocket) — not aligned with current batch architecture |
| **Federated RAG** | Would require multi-node setup, federation protocols — single-node RPi deployment |
| **Long-Context RAG** | Would require long-context model support — Llama3.2 has limited context window |

---

## Infrastructure Notes

### Conversation Memory
- **File**: `src/services/rag-pipeline/repositories/conversation_repository.py` (296 lines)
- **Status**: ✅ **IMPLEMENTED AND ACTIVE** — Used by Conversational RAG
- **Features**: PostgreSQL-backed (`conversation_turns` table), turn ordering, `build_context()` method, `store_turn()` method
- **Enables**: Conversational RAG multi-turn conversations with context continuity

### Clean Architecture (V2)
- **File**: `src/services/rag-pipeline/api_v2.py` (238 lines)
- **Status**: Thin API layer with service separation
- **Extension Points**: `RetrievalService` init has optional slots for `hyde_expander`, `hybrid_searcher`, `reranker`, `crag_retriever`, `parent_child_retriever`, `context_compressor` — **all set to `None`**
- **Could Enable**: Easy integration of unwired modules

---

## Summary

| Bucket | Count | Methods |
|--------|-------|---------|
| **Supported (Production)** | 3 | Standard RAG, Graph RAG, Conversational RAG |
| **Partial (Unwired Modules)** | 8 | RAPTOR (tested), HyDE, Hybrid, Cross-Encoder, Self-RAG, Contextual Compression, Parent-Child, CRAG |
| **Buildable** | 4 | Multi-Query, Decomposition, Metadata Filtering, Modular |
| **Out of Scope** | 4 | Agentic, Streaming, Federated, Long-Context |

**Total methods covered**: 19

> **Takeaway**: Minder has a solid production RAG foundation (Standard + Graph) plus an extensive "research lab" of advanced methods that serve as a code foundation — but most are unverified (import-only checks) and may have runtime bugs when actually run (like graph-rag did). Activating them requires dependency installation, integration wiring, and testing — not straightforward.
