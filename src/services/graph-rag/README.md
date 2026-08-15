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
| POST | `/v1/extract` | spaCy NER — return the entities (+ types) found in `text`, no graph write |
| POST | `/v1/construct-graph` | Extract entities + relationships from `text` and persist them into Neo4j (optionally tagged with a `document_id`) |
| POST | `/v1/retrieve` | Graph-aware retrieval for a query — pull the relevant entity subgraph as context |
| POST | `/v1/entity-context` | The neighbourhood (linked entities/relationships) around a named entity |
| POST | `/v1/graph/search` | Free-text entity search — case-insensitive `CONTAINS` match on entity text/label; returns `{text, label, description}` per hit (`limit` 1–50) |
| GET | `/v1/graph/stats` | Graph overview: node / relationship / document / entity counts + the per-NER-label entity distribution (confirm a build populated the graph) |
| GET | `/v1/graph/documents` | List the Document nodes (id / title / source / entity_count), newest first — browse what's built |
| DELETE | `/v1/graph/document/{document_id}` | Remove all nodes/edges contributed by one document |

Every route is served at both `/v1/...` and the legacy unversioned path.

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

- **Neo4j** — the knowledge graph (shared with marketplace's dependency graph, but
  different node labels). REQUIRED. Graph writes use `MERGE` so re-ingesting a
  document is idempotent. The graph is a single global Neo4j space — there is no
  per-knowledge-base or per-user partitioning of entities/documents. Entities
  merge across documents by `(text, label)` regardless of who/what ingested
  them, and any authenticated caller can list/delete any document (tracked:
  [#628](https://github.com/wish-maker/minder/issues/628)).
- **spaCy** — the NER model; excluded from CI mypy (heavy lib false-positives).

## Error conventions

Platform-wide `{"detail": ...}` shape; Neo4j-down surfaces as a backend 503 rather
than a raw 500. See
**[`docs/api/reference.md` → Error Handling](../../../docs/api/reference.md)**.

## Tests

`tests/unit/test_graph_rag_*.py` — entity extraction and the construct/retrieve
flows with spaCy + the Neo4j driver faked (loaded by-path per the one-process
conftest harness).
