# ADR: Tenancy & Data-Correlation Model

> **Status:** Accepted — Phase 1 in progress. LIVING document; the **Status** section
> tracks per-phase progress for cross-session resume. · **Date:** 2026-08-22 ·
> **Owner decision:** maintainer approved the model below and the phase ordering.
> **Related:** [architecture-review-and-roadmap.md](architecture-review-and-roadmap.md),
> issue #920 (re-scoped from "admin-only?" to per-user config + collection dedup).

## Context — the apparent conflict, and its resolution

Minder must do two things that look opposed: **discover correlations across
collected data** and **keep each user's data private**. The tension dissolves once
we stop asking "share or isolate?" and instead tag every artifact with **who it
belongs to**:

- **Shared reference data (public):** BTC price, weather, news, fund prices — the
  *value* is identical for everyone; only *which* data a user subscribes to is
  personal. No privacy reason to silo it; siloing only bloats the DB.
- **Private personal data:** a user's documents (RAG), personal plugin outputs.
  Genuinely per-user; must be isolated.

**The whole model follows from one tag on every AI-facing artifact:**
`owner_id` (a user's JWT `sub`, or `internal-service`) **+** `visibility`
(`shared` | `private`). The AI's retrieval filter, everywhere, is:

```
visibility = 'shared'  OR  owner_id = <current_user>
```

This lets the AI correlate over **`shared ∪ self`** — rich shared corpus + the
user's own data — while making cross-user private leakage **structurally
impossible** (it's the definition of the query, not a check that can be forgotten).
This is exactly how the AI "writes to and reads from Qdrant/Neo4j correctly": the
write path stamps tenancy, the read path filters on `{shared, self}`.

## Decision — canonical tenancy convention

- **Every AI-facing artifact carries `owner_id: str` and `visibility: 'shared'|'private'`.**
- **`owner_id` resolution is centralized** in `shared/tenancy.py`
  (`resolve_owner_id`): user JWT → `sub` (required; 401 if absent — never collapse a
  missing subject into an empty/other tenant); internal service token →
  `internal-service`. This unifies the three divergent implementations today
  (graph-rag `owner_id`, rag-pipeline `owner_user_id`, marketplace/conversation
  `user_id`) onto one helper and one column name (`owner_id`) going forward.
- **`is_visible_to(current_user, owner_id, visibility)`** is the one access
  predicate: `service`/`admin` → all; `visibility == shared` → all;
  `owner_id is None` → legacy/open (backward-compat during migration, backfilled
  later); else `owner_id == caller`.
- **Legacy null policy:** a null `owner_id` is treated as **shared/open** (matches
  rag-pipeline #943). graph-rag's stricter "null = invisible" (#782) is migrated to
  this convention. Migration backfills real owners and sets `visibility`.

### Per-backend rollout (owner tag today → target)

| Backend | Artifact | Owner today | Target |
|---|---|---|---|
| Postgres | `rag_pipelines` | ✅ `owner_user_id` | rename→`owner_id` + `visibility` |
| Postgres | `conversation_*` | ✅ `user_id` + `conversation_shares` | already closest; align names |
| Postgres | `knowledge_bases` | ❌ | add `owner_id` + `visibility` |
| Neo4j | `Document`/`Entity` (graph-rag) | ✅ `owner_id` | add `visibility` |
| **Qdrant** | rag chunks / RAPTOR nodes | ❌ **(highest-priority gap)** | add `owner_id`+`visibility` to point payload; filter in retrieval |
| Postgres | `plugin_configs` | ❌ global | per-user overlay (see #920 below) |
| InfluxDB | collected series | ❌ | tag by `owner`/fingerprint (Phase 3) |
| MinIO | objects | ❌ bucket-level | per-owner prefix (later) |

## Decision — #920: per-user plugin config + collection dedup

Config stays **user-editable (not admin-only)** but becomes **per-user**, without
duplicating collected data. Current state: `plugin_configs` is keyed by
`plugin_name` alone (`plugin-registry/core/database.py:262`, last-writer-wins) — one
global row, any user overwrites everyone.

1. **Per-user config storage** — re-key to `(plugin_name, owner_id)` (null =
   global default). Read resolution: user override → global default →
   `CONFIG_SCHEMA` default. `owner_id` from the JWT, never a body param.
2. **Separate "what to collect" from "who sees it" — the dedup key is a config
   FINGERPRINT**, not the user: `fingerprint = hash(plugin, normalize(shared_safe_params))`.
   - Public config (`symbol=BTC`) → same fingerprint → collected **once**, stored
     `shared`, fanned out to all subscribers. (Solves DB bloat.)
   - Private config (a param carrying a secret/identity) → fingerprint includes the
     owner → inherently unique → naturally `private`. One mechanism, both cases.
   - A `shared: bool` flag per field in `CONFIG_SCHEMA` declares which params are
     "shared-safe".
3. **Ref-counted collector** — config = a subscription to a fingerprint. One
   collector per unique fingerprint; last unsubscribe → collection stops. (Reuses
   the bundle model's reference-counted teardown pattern.)
4. **Coalesce upstream fetches** by fingerprint (short TTL) — protects the DB and
   rate-limited upstreams (esp. TEFAS #120).
5. **Auth stays JWT-any** — safe once isolation is real (a user writes only their
   own row; admin sets the global default).

Data model sketch:
- `plugin_subscriptions(owner_id, plugin_name, config_json, fingerprint, ...)` —
  per-user, private (interest set is itself sensitive).
- `plugin_collection_state(fingerprint, plugin_name, normalized_params, last_run,
  interval, ref_count)` — shared, one row per unique fingerprint.
- Collected data tagged `fingerprint` + `visibility='shared'`, or
  `owner_id=<user>, visibility='private'` for private-class fingerprints.

## Decision — correlation engine (the vision itself)

No correlation engine exists today; "relationship discovery" is only spaCy NER +
Neo4j string-`MERGE`. Build a **`core/correlation` layer inside graph-rag** that
runs after `construct-graph` and derives edges raw NER misses:

- cross-document co-occurrence scoring,
- embedding-neighbour links (the one place graph-rag legitimately needs embeddings —
  via `shared/ai/ollama_client_base.py`, not a copy of rag-pipeline),
- stronger entity resolution (beyond exact `{text,label}` match; `entity_dedup.py`
  is dedup, not correlation).

Every derived edge/node is tenancy-tagged: derived purely from `shared` → `shared`;
derived from any `private` input → `private` (that owner). Correlation queries run
over `shared ∪ self` per the filter above. This is a feature in graph-rag, **not** a
new service and **not** in rag-pipeline (that would re-fuse the backends we keep apart).

## Consequences

- Correlation + privacy + efficient collection + correct AI store access are all
  satisfied by one convention (`owner_id`/`visibility`) + one dedup key (fingerprint).
- Migrations are additive/nullable → backward-compatible; existing single-user data
  keeps working (null → shared) and is backfilled.

## Open questions (revisit before Phase 3)

- Do per-user config overrides apply to **scheduled** collection (fingerprint-shared,
  as designed) or also to **on-demand** AI-tool calls (naturally per-request)?
- Collected private results: shared series annotated with a subscriber set, vs
  per-owner storage namespaces? (Shared-fingerprinted series is what avoids bloat.)
- MinIO/InfluxDB per-owner partitioning shape.

## Status (update as phases land)

- **2026-08-22** — ADR accepted. **Phase 1 started:** `shared/tenancy.py`
  (`resolve_owner_id`, `Visibility`, `is_visible_to`) + unit tests on branch
  `feat/tenancy-foundation-and-adrs`. Not yet adopted by services; Qdrant/KB
  retrofit pending. #782 (graph-rag owner_id) and #943 (rag pipeline owner) are the
  existing partial implementations this generalizes.
- **Next:** adopt `shared/tenancy.py` in graph-rag + rag-pipeline; add
  `owner_id`+`visibility` to Qdrant payloads and `knowledge_bases`; then Phase 2/3/4.
