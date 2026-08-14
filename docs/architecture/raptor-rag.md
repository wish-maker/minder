# RAPTOR retrieval (#487)

Design decisions for the RAPTOR (Recursive Abstractive Processing for
Tree-Organized Retrieval) method, made before writing the ingest/retrieve
code per #487's own "suggested first step." RAPTOR closes the one gap
`docs/rag-methods.md` flagged as MEDIUM-feasibility and buildable on the
current architecture with no new external service.

## What RAPTOR is, in one paragraph

Standard RAG only ever retrieves flat, fixed-size chunks — fine for
"what does section 3.2 say," bad for "summarize the whole document's
argument," since no single chunk holds that. RAPTOR builds a **tree** on top
of a document's chunks at ingest time: cluster similar chunks, have an LLM
summarize each cluster, embed the summaries, then recursively cluster *those*
summaries into a smaller set, repeating until the tree collapses toward a
root. At query time, the search pool is every node at every level — a broad
question's embedding naturally lands closer to a high-level summary; a
specific one lands closer to a leaf chunk.

## Decisions

### 1. Scope: per-document, opt-in

The tree is built **per document**, not across a whole knowledge base
(simpler, avoids one document's structure leaking into another's, and
matches #487's own "runs once per document at ingest time" framing) — and
it's **opt-in** via a new `build_tree: bool = False` field on
`POST /knowledge-bases/{id}/upload`. Every other upload stays exactly as
fast as it is today; nothing changes for a caller who doesn't ask for a
tree. RAPTOR's ingest cost (N/5-ish extra LLM summarization calls plus their
embeddings) is real and shouldn't be paid by every upload just because one
KB somewhere wants it.

Tree-building is skipped (not an error) below `MIN_CHUNKS_FOR_TREE = 6`
chunks — there's nothing meaningful to cluster in a 2-3 chunk document — and
above `MAX_CHUNKS_FOR_TREE = 300`, to bound ingest latency on a very large
upload (the O(k²) clustering below is fine at hundreds of chunks, not at
tens of thousands).

### 2. Clustering: pure-numpy agglomerative, no new dependency

`scikit-learn`/`scipy` are **not installed** in `rag-pipeline`'s
`requirements.txt` (confirmed against the actual venv). RAPTOR's canonical
approach (GMM soft clustering with BIC-based cluster-count selection) needs
one of those. Given:

- this whole platform's repeated Pi-friendliness constraint (small Piper
  voice tiers, no scikit-learn/scipy anywhere else in this service either),
- the per-document scope keeps N small (tens to a couple hundred chunks,
  not corpus-wide), where an O(k²) naive algorithm is entirely fine, and
- adding a new heavy ML dependency for one retrieval method is a real,
  ongoing image-size/build-time cost on every deployment, including ones
  that never touch RAPTOR,

the implementation is **bottom-up average-linkage agglomerative clustering
over cosine distance**, hand-rolled with `numpy` (already present
transitively via `rank-bm25`) — no new dependency. Target cluster size is
fixed at 5 (i.e., each clustering pass aims to shrink the node count by
~5×); this is simpler than GMM/BIC and, at per-document scale, produces
comparable groupings for the actual goal (chunks that are already similar
end up together).

### 3. Tree depth: adaptive, capped

Clustering repeats until either a level collapses to a single node (the
root reached) or `MAX_TREE_LEVELS = 3` additional levels have been built
(level 0 = leaf chunks, 1-3 = summaries) — whichever comes first. A level
that doesn't actually reduce the node count stops the loop early (nothing
further to gain).

### 4. Summarization: the KB's own LLM, same call as everything else

Each cluster's member texts are concatenated and summarized via
`ollama_manager.generate_response(prompt=..., model=kb["llm_model"])` — the
exact same call HyDE already uses for its hypothetical-answer generation.
No new model config, no new client. `generate_response` never raises (it
returns `{"error": True}` on failure); a failed/empty summary degrades to a
truncated concatenation of the cluster's raw text rather than dropping the
cluster or aborting the tree.

### 5. Storage: same Qdrant collection, two new payload fields

No new collection, table, or store — tree nodes are just more points in the
same `kb_id` collection every other chunk already lives in, carrying the
**same** `kb_id`/`document_id`/`source`/`uploaded_at` payload fields as
their document's leaf chunks. This is deliberate: `delete_document`
(`routes/rag.py`) already deletes by `document_id`, so deleting a document
correctly removes its whole tree with **zero** changes to that code path.

Two new fields:

| Field | On | Meaning |
|---|---|---|
| `tree_level` | every point, leaf and summary | `0` = original chunk (stamped on **every** upload from now on, tree or not — see below), `1..N` = summary level, higher = more abstract |
| `children_ids` | summary nodes only (`tree_level >= 1`) | Qdrant point IDs of the nodes (leaf or lower-level summary) this node summarizes |

`tree_level: 0` is stamped on every leaf chunk **unconditionally**, even
when `build_tree=False` — this is what makes the retrieval-filtering change
below safe and uniform, not something that only kicks in for documents that
opted into trees.

### 6. Retrieval: existing methods stay leaf-only; RAPTOR sees everything

Every point in a collection — leaf or summary — is a valid vector "hit" for
ordinary dense/hybrid/parent-child search, since Qdrant doesn't know or
care what `tree_level` means. Without a guard, turning this on would start
mixing LLM-generated summary text into **every other method's** results the
moment any document in a KB has a tree — a real regression for standard/
HyDE/self_rag/corrective/hybrid/parent_context queries that have nothing to
do with RAPTOR.

Fix: `core/retrieval.py::build_metadata_filter` gains an
`include_all_levels: bool = False` parameter. When `False` (the default,
used by every existing retrieval call site), it ANDs in
`must_not=[FieldCondition(key="tree_level", range=Range(gt=0))]` —
excluding any point whose `tree_level` is explicitly greater than 0.
Critically, a Qdrant field condition **never matches a point missing that
field**, so `must_not=[Range(gt=0)]` is a no-op (doesn't exclude) for every
point ingested *before* this feature shipped, which has no `tree_level` at
all. No backfill/migration needed — old documents keep working exactly as
they do today, with zero data changes.

RAPTOR's own retrieval calls the same dense retriever
(`retrieve_relevant_documents`) with `include_all_levels=True`, which skips
that `must_not` condition entirely — every level is a candidate, plain
cosine top-k across the lot. This is RAPTOR's "**collapsed tree**" retrieval
strategy (one of the two the original paper describes, the simpler of the
two — no level-by-level traversal logic needed, since ordinary similarity
search already does the right thing: a broad question's embedding tends to
land near an abstract summary, a specific one near a leaf).

### 7. API surface: `method: "raptor"`, not a boolean flag

`docs/rag-methods.md` already lists RAPTOR alongside HyDE/Self-RAG/
Corrective as a "method"-tier technique (not alongside `hybrid`/
`parent_context`, which the same doc calls "orthogonal retrieval
strategies"), and #487's own issue text asks for `method: "raptor"` in
`VALID_RAG_METHODS`. Both agree: it lands as a method value, dispatched in
`routes/rag.py`'s retrieval-strategy selector (`routes/rag.py:636-659`)
alongside the `parent_context`/`hybrid`/dense choice — precedence becomes
`parent_context > hybrid > raptor > dense`, with a `retrieval_notes` entry
recorded whenever the raptor request gets pre-empted by an explicit
`hybrid`/`parent_context` flag, matching the existing convention for silent
downgrades.

Choosing `raptor` when a KB's documents have no tree (never opted into
`build_tree`) is not an error — it's just a normal collapsed-tree search
over a set of documents that all happen to have `tree_level: 0` everywhere,
i.e., identical to standard dense retrieval. This degrade path needs no
special-casing.

### Non-goals for this pass

- **Level-by-level tree traversal** (the paper's other retrieval strategy,
  walking down from root to children based on the query) — collapsed-tree
  gets most of the benefit with far less code; can be added later as a
  second `raptor` variant if collapsed-tree proves insufficient in
  practice.
- **Cross-document trees** — explicitly out of scope; #487 scoped this to
  per-document.
- **Background/async tree construction** — this service has no job-queue
  infrastructure; `build_tree=True` extends the upload request's own
  response time (synchronous, like every other ingest step today).
