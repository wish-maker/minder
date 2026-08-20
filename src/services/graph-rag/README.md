# graph-rag

Knowledge-graph construction from text (`:8008`, FastAPI, ~1.3k LOC). Extract
named entities with spaCy NER, wire them into a Neo4j knowledge graph, and
retrieve graph-structured context for a query or a specific entity. Talks only to
**Neo4j + spaCy** — no LLM, no model-management. Interactive docs at `/docs`.

Distinct from rag-pipeline (that's vector RAG over chunks); this is the *graph*
side — entities and their relationships.

## Run / check

```bash
bash setup.sh start graph-rag        # needs Neo4j; the spaCy model is baked into the image

curl http://localhost:8008/health
curl -X POST http://localhost:8008/v1/extract \
     -H 'Content-Type: application/json' -d '{"text":"Ada Lovelace worked with Charles Babbage in London."}'

python scripts/dev/dev.py mypy graph-rag
python -m pytest tests/unit/test_graph_rag_*.py
```

## Endpoints (see `/docs` for schemas)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/v1/extract` | spaCy NER — return the entities (+ types) found in `text`, no graph write. **Open** (touches no graph) |
| POST | `/v1/construct-graph` | Extract entities + relationships from `text` and persist them into Neo4j under a `document_id` (optional `kb_id` grouping). **JWT-required, owner-scoped** |
| POST | `/v1/retrieve` | Graph-aware retrieval for a query — pull the relevant entity subgraph as context. **JWT-required, owner-scoped** |
| POST | `/v1/entity-context` | The neighbourhood (linked entities/relationships) around a named entity. **JWT-required, owner-scoped** |
| POST | `/v1/graph/search` | Free-text entity search — case-insensitive `CONTAINS` match on entity text/label; returns `{text, label, description}` per hit (`limit` 1–50). **JWT-required, owner-scoped** |
| GET | `/v1/graph/stats` | Graph overview: node / relationship / document / entity counts + the per-NER-label entity distribution, **scoped to the caller**. **JWT-required** |
| GET | `/v1/graph/documents` | List the caller's own Document nodes (id / title / source / kb_id / entity_count), newest first. **JWT-required, owner-scoped** |
| DELETE | `/v1/graph/document/{document_id}` | Remove all nodes/edges contributed by one of the caller's documents (a doc owned by another tenant is a no-op). **JWT-required, owner-scoped** |

Every route is served at both `/v1/...` and the legacy unversioned path.

**Per-tenant scoping (#782):** every Document/Entity node carries an `owner_id`
(the authenticated caller's JWT `sub`; the internal service token scopes to
`internal-service`). Nodes are MERGEd on `owner_id`, so two tenants extracting the
same term — or reusing the same `document_id` — get separate nodes, and every
read/traversal/delete is confined to the caller's own graph. One tenant can't see,
retrieve, or delete another's data. Because scoping needs to know the tenant, the
graph reads (`stats`/`documents`/`retrieve`/`entity-context`/`search`) are now
JWT-required (previously open). Pre-#782 nodes have no `owner_id` and are not
visible under any owner — a clean cut-over, not an in-place migration.

## Layout

```
graph-rag/
├── main.py                  # thin app: include the router; Neo4j creds parsed in config
├── routes/api.py            # extract / construct-graph / retrieve / entity-context / delete
├── core/
│   ├── entity_extractor.py  # spaCy NER — text → entities (+ types)
│   ├── graph_constructor.py # entities/relationships → Neo4j MERGE (idempotent)
│   └── graph_retriever.py   # query/entity → relevant subgraph
├── models/schemas.py        # Pydantic request/response models
└── config.py                # Settings: NEO4J_URI, NEO4J_AUTH, SPACY_MODEL
```

## Configuration (`config.py`)

- `NEO4J_URI` (default `bolt://neo4j:7687`).
- `NEO4J_AUTH` — **required**, format `user/password`, parsed fail-fast into
  `(NEO4J_USER, NEO4J_PASSWORD)` (falls back to `NEO4J_USER`/`NEO4J_PASSWORD` env).
- `SPACY_MODEL` (default `en_core_web_sm`) — baked into the image at build time;
  the NER work runs off the event loop so a large document can't stall the service
  (graph-rag NER offload, #497).

## Storage & dependencies

- **Neo4j** — the knowledge graph (shared Neo4j instance with marketplace's
  dependency graph, but different node labels). REQUIRED. Graph writes use `MERGE`
  so re-ingesting a document is idempotent. Entities/documents are **partitioned
  per tenant** by `owner_id` (#782, resolving the isolation gap from #628): entities
  merge across a single owner's documents by `(text, label, owner_id)`, never across
  owners, and a caller can only ever list/retrieve/delete their own documents.
- **spaCy** — the NER model; excluded from CI mypy (heavy lib false-positives).

## Error conventions

Platform-wide `{"detail": ...}` shape; Neo4j-down surfaces as a backend 503 rather
than a raw 500. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_graph_rag_*.py` — entity extraction and the construct/retrieve
flows with spaCy + the Neo4j driver faked (loaded by-path per the one-process
conftest harness).
