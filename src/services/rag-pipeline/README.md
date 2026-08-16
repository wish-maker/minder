# rag-pipeline

Minder's Retrieval-Augmented Generation service (`:8004`, FastAPI). Chunk +
embed uploaded documents into a vector store, then answer questions over them
with local LLM generation. This is Minder's OWN RAG — distinct from OpenWebUI's
disconnected "Knowledge" feature. ~5.7k LOC.

Flow: **knowledge base** (a Qdrant collection + metadata) ← documents you upload
→ **pipeline** (one or more KBs made queryable) → **query** (retrieve relevant
chunks + generate an answer). Interactive docs at `/docs`.

## Run / check

```bash
# From the repo root — the whole stack (rag-pipeline needs qdrant + a reachable
# ollama; postgres is optional but used for durable KB/pipeline/conversation rows):
bash setup.sh start rag-pipeline

# Health + a quick smoke of the flagship flow (verified live many times):
curl http://localhost:8004/health           # {status, ollama_available, knowledge_bases, ...}
curl http://localhost:8004/capabilities      # which retrieval/rerank/compress features are ACTIVE

# Local checks that mirror CI (run from the repo root):
python scripts/dev/dev.py mypy rag-pipeline
DB_PASSWORD=x JWT_SECRET=<32ch> REDIS_PASSWORD=x python -m pytest tests/unit/test_rag_pipeline_*.py
```

> The gateway proxies this service at `/v1/rag/*` (it strips `v1/rag/` and
> forwards the rest), so a browser/client hits e.g. `/v1/rag/knowledge-bases`,
> which lands on the unversioned `/knowledge-bases` alias here. Every route is
> served at BOTH `/v1/...` and the legacy unversioned path (not a redirect —
> that would drop the body on non-GET clients, #147).

## Endpoints (see `/docs` for full schemas)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/knowledge-bases` | Create a KB (`name` required, `description` optional; pick embedding + llm model + chunk sizes). Makes a Qdrant collection |
| GET | `/v1/knowledge-bases` | List KBs — `{items,total,limit,offset}` envelope (#501) |
| GET | `/v1/knowledge-bases/{id}` | Get one KB |
| PATCH | `/v1/knowledge-bases/{id}` | Edit metadata in place — name / description / llm_model (embedding_model + chunk params immutable) (#544). JWT-gated |
| DELETE | `/v1/knowledge-bases/{id}` | Delete a KB (drops its Qdrant collection + PG row). JWT-gated |
| POST | `/v1/knowledge-bases/{id}/upload` | Upload a PDF / TXT / MD. **413** over `MAX_UPLOAD_SIZE_MB` (default 50MB). **503** if the embedding backend is unreachable (no silent zero-vector, #77). One `document_id` per upload |
| GET | `/v1/knowledge-bases/{id}/documents` | List documents (one per upload, not per chunk) — envelope shape |
| GET | `/v1/knowledge-bases/{id}/documents/{doc_id}/chunks` | List a document's actual stored chunk text — diagnostic for a bad extraction/OCR vs. a retrieval issue. Envelope shape |
| DELETE | `/v1/knowledge-bases/{id}/documents/{doc_id}` | Delete one document's chunks. JWT-gated |
| POST | `/v1/pipeline` | Create a pipeline over ≥1 KB (`knowledge_base_ids` min_length 1) |
| GET | `/v1/pipeline` / `/v1/pipeline/{id}` | List / get pipelines |
| PATCH | `/v1/pipeline/{id}` | Edit name / knowledge_base_ids in place (#545). JWT-gated |
| DELETE | `/v1/pipeline/{id}` | Delete a pipeline (its KBs are left intact). JWT-gated |
| POST | `/v1/pipeline/{id}/query` | Retrieve + generate — the flagship endpoint (see below) |
| GET | `/v1/decision-stats` | `method="auto"` routing analytics — total decisions + strategy/complexity distributions + mean confidence. `available:false` when the auto engine isn't up. In-memory (resets on restart) |

**Query body:** `{"question": "...", "top_k": 1-100, "method": "standard|hyde|self_rag|auto|corrective", "conversation_id": "...", "rerank": bool, "compress": bool, "hybrid": bool, "parent_context": bool, "metadata_filter": {"source": "...", "document_id": "..."}}`. Response carries the `answer`, the retrieved `sources` (`{source, score, text}`), and `method_details`. Full method semantics + the capability-adaptive behaviour live in **[`docs/rag-methods.md`](../../../docs/rag-methods.md)**; an unknown `method` (incl. `raptor`) → 422. RAPTOR is the one commonly-cited method NOT implemented (tracked in #487).

## Layout

```
rag-pipeline/
├── main.py                 # thin app: lifespan (state init) + include routers
├── routes/
│   ├── rag.py              # KB / document / pipeline / query endpoints
│   └── system.py           # /health, /capabilities, ollama init
├── core/
│   ├── state.py            # process-global stores (KB/pipeline dicts) + qdrant/PG clients + metrics
│   ├── ingestion.py        # upload → chunk → embed → upsert; group_documents()
│   └── retrieval.py        # the retrieval strategies (dense / hybrid / parent_context), metadata filter
├── rag/
│   ├── runner.py           # orchestrates a query (method → retrieve → generate)
│   ├── model_selection.py  # resolve the LLM per request
│   ├── ollama_manager.py   # shared Ollama client lifecycle (embeddings + generation; failover-aware)
│   └── text_utils.py       # chunking / text helpers
├── domain/
│   ├── decision_engine.py  # `auto` method: pick a strategy per question
│   └── quality_evaluator.py# Self-RAG / Corrective grading heuristics
├── repositories/
│   ├── pg_client.py        # optional Postgres persistence (UPSERT KBs/pipelines)
│   └── conversation_repository.py  # conversational-RAG turn history
├── models/__init__.py      # Pydantic request/response models
└── config.py               # Settings (Qdrant/Ollama/embedding-model/chunk defaults)
```

## Configuration (`config.py`, env-overridable)

- `QDRANT_HOST` / `QDRANT_PORT` — the vector store (`qdrant:6333`).
- `OLLAMA_EMBEDDING_MODEL` (default `nomic-embed-text`) / `OLLAMA_LLM_MODEL` (default `llama3.2`) — embedding + generation models. `EMBEDDING_DIMENSIONS` maps a model → its vector size for the collection.
- `OLLAMA_HOST` (from the shared base settings) — where embeddings/generation go; the platform-level `OLLAMA_BASE_URL` (compose/.env) drives it: empty = the local `minder-ollama` container, set = an external/native host (resolve as `host.docker.internal`/LAN-IP, not `localhost`, since the CONTAINER resolves it). `OLLAMA_FAILOVER_PRIMARY` names the external primary the ollama-router prefers in failover mode.
- `MODEL_MANAGEMENT_URL` — the model-management service, consulted for model resolution.
- Secrets (`DB_PASSWORD`/`REDIS_PASSWORD`/`JWT_SECRET`) come from `MinderBaseSettings` and are required.

## Storage & dependencies

- **Qdrant** — one collection per KB (vectors). REQUIRED.
- **Ollama** — embeddings (ingest) + generation (query). A query needs a REACHABLE ollama at `OLLAMA_BASE_URL`; if it's down, upload 503s (no silent zero-vector) and query returns an error (#77).
- **Postgres** — optional durable rows for KBs / pipelines / conversation history (the in-memory `state` dicts are the source of truth at runtime; PG is write-through via UPSERT).
- Sync Qdrant/embedding calls run off the event loop via `asyncio.to_thread` (#211) so one slow op can't stall the service.
- Qdrant upserts during ingestion are batched (`QDRANT_UPSERT_BATCH_SIZE`, mirrors the embedding phase's own batching, #683) — on a mid-document failure, already-written points for that upload are deleted so the upload still fails atomically overall. KB `document_count`/`vector_count` are reconciled from Qdrant's actual point count on startup (#629), rather than trusting a possibly-stale Postgres row.

## Tests

`tests/unit/test_rag_pipeline_*.py` (loaded by-path, since conftest loads every
service into one process — see the harness note in
`test_rag_pipeline_retrieval.py`): retrieval strategies + metadata filter,
ingestion, model selection, the envelope shapes, the PATCH edit endpoints, and
the auth gates. Live flows run in `tests/e2e/test_rag_flow.py`.
