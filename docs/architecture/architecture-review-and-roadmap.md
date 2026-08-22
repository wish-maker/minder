# ADR: Architecture Review & Refactor Roadmap

> **Status:** Accepted — execution in progress (Phase 1 started). This is a LIVING
> document: the **Progress / Status** section at the bottom is updated as each slice
> lands so any session (or contributor) can resume from the current state. ·
> **Date:** 2026-08-22 · **Owner decision:** approved by the maintainer to
> prioritize, plan, and execute; re-evaluate as we go.

## Context

A full, code-grounded review of the service topology was run (three parallel
readers over the plugin triad, the retrieval/inference services, and the
cross-cutting gateway/`shared`/tenancy layer). The platform's vision is
**cross-data correlation / relationship discovery** while **simultaneously**
enforcing **per-user data privacy** — and having the AI write to / read from the
backing stores (Qdrant, Neo4j, …) correctly scoped to that privacy model.

The architecture is **fundamentally sound**: Postgres is single-writer per service
(table-namespaced, no cross-writes), Qdrant is single-writer (rag-pipeline), and
`shared/`'s core (errors/log/metrics/health/auth/config) is adopted by 7–8 of the 8
Python services. The problems are localized, not systemic: **two structural moves,
one cross-cutting inconsistency (tenancy), and a handful of cleanups.**

Service census (LOC = routes+core+domain+repositories; 2026-08-22):

| Service | LOC | Routes | Postgres tables | Verdict |
|---|---:|---:|---|---|
| rag-pipeline | 7178 | 48 | 5 | Keep (fat, cohesive) |
| plugin-registry | 4441 | 34 | 3 | Keep (absorbs psm) |
| marketplace | 3701 | 33 | 11 | Keep (clean commerce/catalog boundary) |
| api-gateway | 2527 | 33 | 1 | Keep — but split out `routes/ai.py` |
| plugin-state-manager | 2220 | 15 | 3 | **Merge → plugin-registry** |
| graph-rag | 1798 | 16 | 0 (Neo4j) | Keep + **invest** (correlation home) |
| tts-stt | 802 | 9 | 0 | Keep as-is (rightsized) |
| model-management | 737 | 16 | 0 | Keep; drop 3× 501 stub routes |

## Decisions

### Merge / Split (two structural moves — both maintainer-approved)

1. **MERGE `plugin-state-manager` → `plugin-registry`.** psm (1846 LOC routes+core)
   is a thin orchestrator that keeps calling back into registry (`state.py:73`
   existence check; `execution.py:252-282` action dispatch). The tool-execute flow
   adds a needless hop (psm → marketplace lookup → psm license check → registry
   dispatch) when registry already aggregates the same tool defs
   (`ai_tools.py:70`). Two concrete duplications collapse with the merge:
   - **Dependency graph exists twice**: marketplace Neo4j graph **+** psm
     `plugin_dependencies` table → pick one owner.
   - **Two license subsystems**: marketplace (user-keyed, real) **+** psm
     `plugin_states.license_tier/key` (plugin-keyed, `#47` fail-closed **stub**) →
     collapse to marketplace as the single license authority; psm's per-plugin
     license path (`core/license.py:137-253`, `routes/licensing.py`) is redundant.
   psm's only unique concerns — the `plugin_states` table + default-plugin
   bootstrap — sit naturally next to registry's `plugins`/`plugin_configs`.

2. **SPLIT `api-gateway/routes/ai.py` (613 LOC) → its own orchestration/agent
   service.** It is not gateway work: tool synthesis (`ask_<pipeline>` generation),
   a multi-turn tool loop (`MAX_TOOL_ITERATIONS=5`), model-quirk normalization
   (command-r / qwen envelope parsing), cross-service dispatch, and on-the-fly
   OpenAPI generation. It's larger than the whole proxy layer, is stateful and
   model-aware, and will grow into the AI "brain" as the correlation vision lands —
   extract it now, let the gateway proxy `/v1/ai/*` like every other route.

### Keep (no split; internal refactor only)

- **marketplace** — the only commerce/catalog/multi-user boundary; pure server, no
  outbound HTTP. Keep independent.
- **rag-pipeline** — fat but cohesive. Internal refactor: consolidate the **twin
  RAG-method trees** `domain/` (2287 LOC) vs `rag/methods/` (1141 LOC) —
  corrective/hyde/etc. exist in both.
- **graph-rag** — keep and invest: this is the strategic core where the correlation
  engine must be built (see the tenancy+correlation ADR).
- **model-management** — thin (737 LOC) but operationally justified (admin-gated
  pulls, pull-concurrency semaphore, rate-limited test). Cleanup: **remove the 3×
  `501` stub routes** (constraints/metrics/fine-tune) from the public surface —
  they advertise capability the service has decided not to own.
- **tts-stt** — correctly single-purpose, stateless, internal-only. Do not touch.
- **rag-pipeline ⇄ graph-rag — do NOT merge.** Complementary halves of retrieval,
  backend-disjoint (Qdrant vs Neo4j), zero shared code. Fuse *results* at the
  caller, never the services.

### Missing (strategic gaps)

- **No correlation / inference engine.** Today "relationship discovery" = graph-rag
  spaCy NER + Neo4j `MERGE {text,label,owner_id}` (same string → one node). No
  co-occurrence / embedding-neighbour / temporal correlation, no entity resolution
  beyond exact match. The platform's core vaunted capability does not exist yet.
  Home: a new `core/correlation` layer **inside graph-rag** (Phase 3).
- **No shared tenancy layer.** Ownership is done with **three different column
  names** (graph-rag `owner_id`, rag-pipeline `owner_user_id`,
  marketplace/conversations `user_id`) and **two different null-owner policies**
  (graph-rag: null = invisible; rag-pipeline: null = open), copy-pasted per service.
  → `shared/tenancy.py` (Phase 1, this ADR's first slice).
- **No `shared/db/neo4j.py`.** Neo4j has two independent drivers (graph-rag +
  marketplace `core/neo4j_client.py`); the `shared/db/pool.py` equivalent is missing.
- **AI-facing artifacts with no owner tag:** **Qdrant points** (the actual RAG
  content vectors — ownership is only indirect via the pipeline!), `knowledge_bases`,
  InfluxDB series, MinIO objects. Qdrant is the highest-priority gap.

### Excessive (cleanup)

- Two single-consumer modules misfiled in `shared/`: `bundle_graph.py` (276 LOC) and
  `ai/tool_validator.py` — both used only by plugin-registry → move them in.
- Two live AI-tool catalogs: registry `/v1/plugins/ai/tools` (gateway consumes) +
  marketplace `/v1/marketplace/ai/tools` (psm consumes) → establish one source of
  truth.
- psm's redundant per-plugin license path (folds into the psm→registry merge).
- Duplicate dependency graph (marketplace Neo4j + psm table).
- Twin RAG-method trees inside rag-pipeline.

## Prioritized roadmap (phases)

1. **Phase 1 — Tenancy foundation** (highest value, vision-critical, low risk):
   `shared/tenancy.py` (canonical owner + `visibility`) → normalize the divergent
   column names → retrofit `owner_id`/`visibility` onto **Qdrant points** and
   `knowledge_bases`. Establishes the privacy boundary the whole vision rests on.
2. **Phase 2 — Extract the orchestration service** from `api-gateway/routes/ai.py`
   (structural; do before the correlation engine makes it grow further).
3. **Phase 3 — Per-user plugin config + collection dedup (#920)**: fingerprint-keyed
   shared collection + ref-counted collector (see tenancy ADR).
4. **Phase 4 — Correlation engine** in graph-rag, honouring the `shared ∪ self`
   tenancy filter.
5. **Cleanup (parallel, low risk):** psm→registry merge, drop 501 routes, move the
   two misfiled `shared/` modules, add `shared/db/neo4j.py`, consolidate the twin
   RAG-method trees.

## Consequences

- One fewer deployable after the psm→registry merge; one more after the
  orchestration split — net neutral count, better cohesion.
- A single tenancy convention makes the privacy guarantee auditable in one place
  and unblocks correlation over `shared ∪ self`.
- Backward-compatible migrations throughout (nullable owner columns, additive
  schema), matching the #782/#943 cut-over pattern already in use.

## Progress / Status (update as slices land — resume anchor)

- **2026-08-22** — ADRs written; **Phase 1 started**. `shared/tenancy.py` +
  unit tests landed on branch `feat/tenancy-foundation-and-adrs` (canonical
  `resolve_owner_id` / `Visibility` / `is_visible_to`). Adoption into graph-rag /
  rag-pipeline and the Qdrant/`knowledge_bases` `owner_id` retrofit are the next
  Phase-1 slices (not yet done).
- Prereqs merged this session (foundations the vision builds on): **#943**
  pipeline owner-scoping (PR #951), **#948/#949** (PR #950). **#920** re-scoped
  with a design plan (see tenancy ADR).
- **Next up:** finish Phase 1 — adopt `shared/tenancy.py` in graph-rag (replace
  `_owner_id`) and rag-pipeline; add `owner_id` to Qdrant point payloads
  (`rag-pipeline/core/ingestion.py`) + a `visibility` column to `knowledge_bases`,
  with the retrieval filter applied in `core/retrieval.py`.
